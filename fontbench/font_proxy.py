from __future__ import annotations
from pathlib import Path
from collections import defaultdict
from typing import Optional, Iterator
from dataclasses import dataclass

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
# from fontTools.pens.boundsPen import BoundsPen
from fontTools.varLib.models import normalizeLocation
from fontTools.varLib.varStore import VarStoreInstancer
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.ttLib.ttFont import TTFont
from fontTools.ttLib.ttGlyphSet import _TTGlyphGlyf as TTGlyph

from fontbench.font_enums import Name, Platform, WindowsEncoding, WindowsLanguage


@dataclass
class AxisProxy:
    tag: str
    min: float
    max: float
    default: float

    def __repr__(self):
        return f'AxisProxy({self.tag}, {self.default}, {self.min} -- {self.max})'


@dataclass
class MasterProxy:
    
    def __init__(self, font: FontProxy, name: str, coordinates: dict[str, float]):
        self.font = font
        self.name = name
        self.coordinates = coordinates
        self.glyphs = self.font.font.getGlyphSet(location=self.coordinates)
    
    def __repr__(self):
        return f'MasterProxy("{self.name}", {self.coordinates})'
    
    def get_glyph(self, glyph_identifier: str) -> GlyphProxy | None:
        # if glyph_identifier not in self.glyphs:
        #     return None
        # return GlyphProxy(self, self.glyphs[glyph_identifier])
        return self.font.get_glyph(glyph_identifier, self.name)
    
    def iter_glyphs(self, include_unencoded: bool = False) -> Iterator[GlyphProxy]:
        # for glyph_id in self.font.get_all_glyph_names(include_unencoded):
        #     yield self.get_glyph(glyph_id)
        for glyph in self.font.iter_glyphs(include_unencoded, self.name):
            yield glyph


class GlyphProxy:

    def __init__(self, master: MasterProxy, glyph: TTGlyph):
        self.font = master.font
        self.master = master
        self.glyph = glyph
        self.glyph_id = glyph.name
    
    def __repr__(self):
        return f'GlyphProxy("{self.glyph_id}" {self.string})'
    
    @property
    def string(self) -> str | None:
        codepoints = self.font.glyph_codepoints.get(self.glyph_id)
        if not codepoints:
            return None
        # if len(codepoints) > 1:
        #     chars = [f"U+{cp:04X}" for cp in codepoints]
        #     # print(f"{name}: {chars}")
        #     return chars
        return chr(codepoints[0])
    
    @property
    def layers(self):
        raise NotImplementedError('Layers are not supported yet.')
    
    @property
    def height(self) -> float:
        return self.font.ascender - self.font.descender
    
    @property
    def width(self) -> float:
        if not self.font.is_variable:
            return self.glyph.width
        
        default_width = self.font.font['hmtx'].metrics[self.glyph_id][0]

        # For variable fonts, compute interpolated width
        # Use HVAR if available (more efficient), otherwise fall back to gvar phantom points
        if 'HVAR' in self.font.font:
            return self._get_width_from_hvar(default_width)
        else:
            return self._get_width_from_gvar(default_width)
    
    def _get_width_from_hvar(self, default_width: float) -> float:
        '''Get interpolated width using HVAR table (Horizontal Metrics Variations).'''        
        hvar = self.font.font['HVAR'].table
        fvar = self.font.font['fvar']
        
        # Create instancer for the variation store
        instancer = VarStoreInstancer(hvar.VarStore, fvar.axes, self.master.coordinates)
        
        # Get the delta-set index for this glyph
        if hvar.AdvWidthMap:
            # Font has explicit mapping from glyph to delta-set
            idx = hvar.AdvWidthMap.mapping[self.glyph_id]
        else:
            # Implicit mapping: glyph index == delta-set inner index
            idx = self.font.font.getGlyphID(self.glyph_id)
        
        # Get the delta at this location
        delta = instancer[idx]
        return default_width + delta
    
    def _get_width_from_gvar(self, default_width: float) -> float:
        '''Get interpolated width from gvar phantom points (when HVAR is absent).'''
        gvar = self.font.font.get('gvar')
        if gvar is None:
            return default_width
        variations = gvar.variations.get(self.glyph_id)
        if not variations:
            return default_width
        
        # Normalize location coordinates to [-1, 1] range
        location = normalizeLocation(self.master.coordinates, self.font.axes_dict)
        
        # Calculate width delta from all variation tuples
        width_delta = 0.0
        for var in variations:
            if var.coordinates is None:
                continue
            
            # Phantom points are at the END of coordinates:
            # [-4] origin, [-3] advance width, [-2] top origin, [-1] top advance
            advance_delta = var.coordinates[-3] if len(var.coordinates) >= 3 else None
            if advance_delta is None:
                continue
            
            # Calculate scalar for this variation tuple based on location
            scalar = 1.0
            for axis_tag, (min_val, peak, max_val) in var.axes.items():
                if axis_tag not in location:
                    scalar = 0.0
                    break
                loc_val = location[axis_tag]
                if loc_val == peak:
                    continue
                elif loc_val < peak:
                    if peak == min_val or loc_val <= min_val:
                        scalar = 0.0
                        break
                    scalar *= (loc_val - min_val) / (peak - min_val)
                else:
                    if peak == max_val or loc_val >= max_val:
                        scalar = 0.0
                        break
                    scalar *= (max_val - loc_val) / (max_val - peak)
            
            if scalar != 0:
                delta_x = advance_delta[0] if isinstance(advance_delta, tuple) else advance_delta
                width_delta += scalar * delta_x
        
        return default_width + width_delta
        
    
    def to_svg_code(self, full_svg: bool = True, output_path: Optional[str | Path] = None) -> str:
        width = self.width
        # If glyph go out of bounds, maybe should use glyph's bounds instead?
        height = self.height
        
        # Draw the glyph
        pen = SVGPathPen(self.master.glyphs)
        self.glyph.draw(pen)
        svg_path = f'<path d="{pen.getCommands()}" fill="black"/>'
        if not full_svg:
            return svg_path
        svg_code = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" style="background-color: white;" viewBox="0 {-self.font.ascender} {width} {height}"><g transform="scale(1,-1)">{svg_path}</g></svg>'
        
        if output_path:
            with Path(output_path).open('w') as f:
                f.write(svg_code)
        return svg_code


class FontProxy:

    def __init__(self, path: str | Path, load_masters: bool = True):
        self.path = Path(path)
        self.font = TTFont(self.path)
        
        for table_name in ('name', 'head'):
            assert table_name in self.font, f'Font must have a "{table_name}" table.'
        
        self.name_table = self.font['name']
        self.head_table = self.font['head']
        # self.cmap_table = self.font['cmap']
        self.glyf_table = self.font['glyf']
        self.cmap_table = self.font.getBestCmap()
        
        # Note some glyphs can have multiple codepoints
        # For example, space and non-breaking space may share a glyph
        self.glyph_codepoints = defaultdict(list)
        for codepoint, glyph_name in self.cmap_table.items():
            self.glyph_codepoints[glyph_name].append(codepoint)

        self.masters = {}
        if self.is_variable:
            for instance in self.font['fvar'].instances:
                master_name = self.get_name(instance.subfamilyNameID)
                self.masters[master_name] = MasterProxy(self, master_name, instance.coordinates)
        self.master = self.masters[self.subfamily]  # Default master
    
    def __repr__(self):
        return f'FontProxy ({self.path.name}): {self.family_name} {self.subfamily}'
    
    def get_name(self, name_id: Name, prefer_chinese: bool = True) -> str | None:
        # TODO: Also consider Unicode and Mac platforms
        language_priorities = [WindowsLanguage.ENGLISH_US, WindowsLanguage.ENGLISH_UK, None]
        if prefer_chinese:
            language_priorities[:0] = [WindowsLanguage.CHINESE_PRC, WindowsLanguage.CHINESE_HONG_KONG, WindowsLanguage.CHINESE_TAIWAN, WindowsLanguage.CHINESE_MACAO]
        priorities = [
            (Platform.WINDOWS, WindowsEncoding.UNICODE_BMP),
            (Platform.WINDOWS, WindowsEncoding.UNICODE_FULL),
        ]

        for platform, encoding in priorities:
            for language in language_priorities:
                if language is None:
                    record = self.name_table.getName(name_id, platform, encoding)
                else:
                    record = self.name_table.getName(name_id, platform, encoding, language)
                if record:
                    return record.toUnicode()
        
        # Nothing found, resort to default method
        return self.name_table.getDebugName(name_id)
    
    @property
    def family_name(self) -> str:
        return self.get_name(Name.FAMILY)
    
    @property
    def subfamily(self) -> str:
        return self.get_name(Name.SUBFAMILY)
    
    @property
    def full_name(self) -> str:
        return self.get_name(Name.FULL_NAME)

    @property
    def postscript_name(self) -> str:
        return self.get_name(Name.POSTSCRIPT_NAME)

    @property
    def unique_id(self):
        return self.get_name(Name.UNIQUE_ID)
    
    @property
    def designer(self) -> str:
        return self.get_name(Name.DESIGNER)
    
    @property
    def version(self) -> str:
        return self.get_name(Name.VERSION)
    
    @property
    def upm(self) -> int:
        return self.head_table.unitsPerEm
    
    @property
    def ascender(self) -> int:
        if 'OS/2' in self.font:
            return self.font['OS/2'].sTypoAscender
        return self.font['hhea'].ascender
    
    @property
    def descender(self) -> int:
        if 'OS/2' in self.font:
            return self.font['OS/2'].sTypoDescender
        return self.font['hhea'].descender
    
    @property
    def is_variable(self) -> bool:
        return 'fvar' in self.font
    
    @property
    def axes(self) -> list[AxisProxy]:
        if not self.is_variable:
            return []
        return [AxisProxy(ax.axisTag, ax.minValue, ax.maxValue, ax.defaultValue) for ax in self.font['fvar'].axes]
    
    @property
    def axes_dict(self) -> dict[str, tuple[float, float, float]]:
        return {ax.axisTag: (ax.minValue, ax.defaultValue, ax.maxValue) for ax in self.font['fvar'].axes}

    def get_all_glyph_names(self, include_unencoded: bool = False) -> list[str]:
        '''
        Get the names of all glyphs in the font.
        If include_unencoded is True, include glyphs that are unencoded (e.g. ligatures, components, stylistic alternatives).
        '''
        if include_unencoded:
            return self.font.getGlyphOrder()
        else:
            return list(self.font.getBestCmap().values())
    
    def get_glyph(self, glyph_identifier: str, master_name: Optional[str] = None) -> GlyphProxy | None:
        if master_name is not None:
            if master_name not in self.masters:
                raise ValueError(f'Master "{master_name}" not found in font.')
            master = self.masters[master_name]
        else:
            master = self.master
        
        if len(glyph_identifier) == 1:
            # If length is 1, the identifier is the glyph character, we first convert to actual ID
            glyph_identifier = self.cmap_table.get(ord(glyph_identifier))
            if not glyph_identifier:
                return None

        # Identifier should now be a glyph ID (e.g. 'asterisk' or 'uniFF41)
        if glyph_identifier not in master.glyphs:
            return None
        
        glyph = master.glyphs[glyph_identifier]
        return GlyphProxy(master, glyph)
    
    def iter_glyphs(self, include_unencoded: bool = False, master_name: Optional[str] = None) -> Iterator[GlyphProxy]:
        for glyph_id in self.get_all_glyph_names(include_unencoded):
            yield self.get_glyph(glyph_id, master_name)
    
    def get_variable_instance(self, coordinates: dict[str, float]) -> FontProxy:
        '''
        Returns a new FontProxy object with the variable font instantiated at the given coordinates.
        '''
        if not self.is_variable:
            raise ValueError('Font is not a variable font.')
        return FontProxy(instantiateVariableFont(self.font, coordinates))
