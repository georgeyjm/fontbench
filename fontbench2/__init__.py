'''
Measures glyphs in Chinese typefaces so that each glyph can be judged against reference fonts.

Results are plain Python objects; file formats, caching and presentation are left to the scripts using it.
'''

from fontbench2.sources import (
    open_font,
    Box,
    Font,
    Glyph,
    CompiledFont,
    CompiledGlyph,
    GlyphsFont,
    GlyphsGlyph,
)
from fontbench2.metrics import (
    coverage,
    outline_statistics,
    lightness,
)
from fontbench2.strokes import (
    stroke_count,
    stroke_counts,
    stroke_table_info,
)

__all__ = [
    'open_font',
    'Box',
    'Font',
    'Glyph',
    'CompiledFont',
    'CompiledGlyph',
    'GlyphsFont',
    'GlyphsGlyph',
    'coverage',
    'outline_statistics',
    'lightness',
    'stroke_count',
    'stroke_counts',
    'stroke_table_info',
]
