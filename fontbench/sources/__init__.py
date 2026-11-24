from pathlib import Path

from glyphsLib import GSFont

from fontbench.sources.base import Box, Font, Glyph
from fontbench.sources.compiled import CompiledFont, CompiledGlyph
from fontbench.sources.glyphs import GlyphsFont, GlyphsGlyph


_COMPILED_SUFFIXES = ('.ttf', '.otf', '.ttc', '.otc')


def open_font(source: str | Path | GSFont, font_number: int | None = None) -> Font:
    '''
    Opens a font from a .glyphs file, an already parsed GSFont, or a compiled font file.

    Arguments:
        source: Path to the font, or a parsed GSFont.
        font_number: Which font to open from a collection (TTC/OTC).
    '''
    if isinstance(source, GSFont):
        return GlyphsFont(source)
    path = Path(source)
    suffix = path.suffix.lower()
    if suffix == '.glyphs':
        return GlyphsFont(path)
    if suffix in _COMPILED_SUFFIXES:
        return CompiledFont(path, font_number)
    raise ValueError(f'Unsupported font file type "{suffix}": {path}')


__all__ = [
    'open_font',
    'Box',
    'Font',
    'Glyph',
    'CompiledFont',
    'CompiledGlyph',
    'GlyphsFont',
    'GlyphsGlyph',
]
