from pathlib import Path
from dataclasses import dataclass

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib.ttGlyphSet import _TTGlyphGlyf as TTGlyph

from fontbench.font_enums import Name, Platform, WindowsEncoding, WindowsLanguage


@dataclass
class AxisProxy:
    tag: str
    min: float
    max: float
    default: float


@dataclass
class MasterProxy:
    name: str
    coordinates: dict[str, float]


class GlyphProxy:

    def __init__(self, font: FontProxy, glyph_id: str):
        self.font = font
        self.glyph_id = glyph_id
        self.glyph = self.font.glyphs.get(glyph_id)
    
    def __repr__(self):
        return f'GlyphProxy ({self.glyph_id}): {self.glyph.name}'
    
    @property
    def layers(self):
        pass


class FontProxy:

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.font = TTFont(self.path)
        for table_name in ('name', 'head'):
            assert table_name in self.font, f'Font must have a "{table_name}" table.'
        
        self.name_table = self.font['name']
        self.head_table = self.font['head']
        self.cmap_table = self.font['cmap']
        self.glyphs = self.font.getGlyphSet()
    
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
        return self.font.head_table.unitsPerEm
    
    @property
    def ascender(self):
        if 'OS/2' in self.font:
            return self.font['OS/2'].sTypoAscender
        return self.font['hhea'].ascender
    
    @property
    def descender(self):
        if 'OS/2' in self.font:
            return self.font['OS/2'].sTypoDescender
        return self.font['hhea'].descender
    
    # @property
    # def all_glyph_names(self):
    #     return self.font.getGlyphOrder()
    
    @property
    def is_variable(self):
        return 'fvar' in self.font
    
    @property
    def axes(self):
        if not self.is_variable:
            return []
        return [
            {'tag': axis.axisTag, 'min': axis.minValue, 'max': axis.maxValue, 'default': axis.defaultValue}
            for axis in self.font['fvar'].axes
        ]
    
    @property
    def masters(self):
        if not self.is_variable:
            return []
        return [
            {
                'name': self.name_table.getDebugName(inst.subfamilyNameID),
                'coordinates': dict(inst.coordinates),
            }
            for inst in self.font['fvar'].instances
        ]
    
    def get_glyph(self, glyph_identifier: str) -> GlyphProxy | None:
        if len(glyph_identifier) == 1:
            # If length is 1, the identifier is the glyph character, we first convert to actual ID
            glyph_identifier = self.cmap_table.get(ord(glyph_identifier))
            if not glyph_identifier:
                return None

        # Identifier should now be a glyph ID (e.g. 'asterisk' or 'uniFF41)
        if glyph_identifier not in self.glyphs:
            return None
        
        return GlyphProxy(self, glyph_identifier)


#     def get_glyph(self, name) -> GlyphInfo:
#         glyph = self.glyphs[name]
        
#         # Get SVG path
#         svg_pen = SVGPathPen(self.glyphs)
#         glyph.draw(svg_pen)
        
#         # Get bounds
#         bounds_pen = BoundsPen(self.glyphs)
#         glyph.draw(bounds_pen)
        
#         return GlyphInfo(
#             name=name,
#             width=glyph.width,
#             bounds=bounds_pen.bounds,
#             svg_path=svg_pen.getCommands(),
#         )
    
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
