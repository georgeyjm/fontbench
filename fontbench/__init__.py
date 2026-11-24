'''
Measures glyphs in Chinese typefaces so that each glyph can be judged against reference fonts.

Results are plain Python objects; file formats, caching and presentation are left to the scripts using it.
'''

from fontbench.sources import (
    open_font,
    Box,
    Font,
    Glyph,
    CompiledFont,
    CompiledGlyph,
    GlyphsFont,
    GlyphsGlyph,
)
from fontbench.metrics import (
    coverage,
    outline_statistics,
    lightness,
)
from fontbench.measure import (
    GlyphMeasurement,
    FontMeasurement,
    SkipReason,
    measure_glyph,
    measure_font,
)
from fontbench.reference import (
    normalize,
    shape_summary,
    ShapeSummary,
    ReferenceSettings,
    CharReference,
    Reference,
    build_reference,
    ToneCurve,
    fit_tone_curve,
    Deviation,
    Comparison,
    compare,
    FitEvaluation,
    evaluate_fit,
)
from fontbench.charsets import (
    chars_9169,
    tongyong_guifan,
    tongyong_guifan_level,
)
from fontbench.strokes import (
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
    'GlyphMeasurement',
    'FontMeasurement',
    'SkipReason',
    'measure_glyph',
    'measure_font',
    'normalize',
    'shape_summary',
    'ShapeSummary',
    'ReferenceSettings',
    'CharReference',
    'Reference',
    'build_reference',
    'ToneCurve',
    'fit_tone_curve',
    'Deviation',
    'Comparison',
    'compare',
    'FitEvaluation',
    'evaluate_fit',
    'chars_9169',
    'tongyong_guifan',
    'tongyong_guifan_level',
    'stroke_count',
    'stroke_counts',
    'stroke_table_info',
]
