from __future__ import annotations
from pathlib import Path
from collections import defaultdict
from typing import Optional, Iterator
from dataclasses import dataclass

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
# from fontTools.pens.boundsPen import BoundsPen
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
    
    def to_svg_code(self, full_svg: bool = True, output_path: Optional[str | Path] = None) -> str:
        width = self.glyph.width
        # If glyph go out of bounds, maybe should use glyph's bounds instead?
        height = self.font.ascender - self.font.descender
        
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



#     def glyph_to_svg(self, name):
#         glyph = self.get_glyph(name)
#         width = glyph.width
#         height = self.ascender - self.descender
        
#         return f'''<svg xmlns='http://www.w3.org/2000/svg'
#      width='{width}' height='{height}'
#      viewBox='0 {-self.ascender} {width} {height}'>
#   <g transform='scale(1,-1)'>
#     <path d='{glyph.svg_path}' fill='black'/>
#   </g>
# </svg>'''


# Usage
# font = Font('Roboto-Bold.ttf')

# print(font.family_name)      # 'Roboto'
# print(font.designer)         # 'Christian Robertson'
# print(font.units_per_em)     # 2048

# glyph = font.get_glyph('A')
# print(glyph.width)           # 1395
# print(glyph.svg_path)        # 'M 550 0 L ...'

# svg = font.glyph_to_svg('A')
