'''
Measures every character of a font master and returns the results as plain dataclasses.

Results are keyed by character rather than glyph name: references compare the same character across fonts,
and glyph names differ from font to font. `dataclasses.asdict` turns any result into plain dicts for JSON or
pandas, and the classes pickle as they are.
'''

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Iterable

from fontbench2.metrics import lightness, outline_statistics
from fontbench2.sources import Box, Font, Glyph
from fontbench2.strokes import Convention, stroke_count


class SkipReason(StrEnum):
    '''Why measure_font did not measure a character. Values are plain strings, so they serialize as-is.'''
    # The font has no glyph for the character
    NOT_IN_FONT = 'not in font'
    # The font maps the character to a glyph, but that glyph has no layer in the measured master
    NO_GLYPH_IN_MASTER = 'no glyph in master'
    # Zero advance width (or zero ascender-to-descender height), so coverage is undefined
    EMPTY_FRAME = 'empty frame'
    # The glyph has no ink: a space, or a glyph not drawn yet
    NO_OUTLINE = 'no outline'


@dataclass(frozen=True)
class GlyphMeasurement:
    '''
    Measurements of the glyph a font uses for one character, in one master. The font, master and stroke
    convention are recorded once on the FontMeasurement that holds it.
    '''
    char: str
    glyph_name: str
    advance: float
    # Ink area / frame area (advance width x descender-to-ascender), overlaps counted once
    coverage: float
    # CIE L* of the coverage: 100 = blank paper, 0 = solid black
    lightness: float
    # Total strokes of the character (not the glyph) under FontMeasurement.stroke_convention;
    # None for characters without a count, e.g. anything that is not an ideograph
    strokes: int | None


@dataclass(frozen=True)
class FontMeasurement:
    '''
    Measurements of every measured character in one master of a font.
    '''
    # Identifies the font and master across runs; family and master unless the caller chose one
    font_id: str
    family: str
    master: str
    stroke_convention: Convention
    by_char: dict[str, GlyphMeasurement] = field(default_factory=dict)
    # Characters that were not measured, and why
    skipped: dict[str, SkipReason] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.by_char)


def measure_glyph(glyph: Glyph, char: str | None = None, stroke_convention: Convention = 'mainland') -> GlyphMeasurement:
    '''
    Measures one glyph. Unlike measure_font, nothing is skipped: a glyph without ink has coverage 0.

    Arguments:
        glyph: The glyph to measure.
        char: The character the measurement is for. Defaults to the glyph's first character.
        stroke_convention: Which stroke counts to use (see fontbench2.strokes).

    Raises:
        ValueError: The glyph's frame is empty (zero advance width), or `char` is None and the glyph is unencoded.
    '''
    char = char if char is not None else glyph.char
    if char is None:
        raise ValueError(f'Glyph "{glyph.name}" is unencoded; pass the character it should be measured for.')
    frame = glyph.frame
    if frame.area <= 0:
        raise ValueError(f'Glyph "{glyph.name}" has an empty frame.')
    return _record(glyph, char, frame, _ink_area(glyph), stroke_convention)


def measure_font(
    font: Font,
    master: str | None = None,
    chars: Iterable[str] | None = None,
    stroke_convention: Convention = 'mainland',
    font_id: str | None = None,
    progress: Callable[[Iterable], Iterable] | None = None,
) -> FontMeasurement:
    '''
    Measures every character of one font master.

    Glyphs without ink or with an empty frame are not measured; they are listed in `skipped` with the reason.
    A glyph mapped to several characters is measured once and recorded for each of them.

    Arguments:
        font: The font to measure.
        master: Which master (or named instance); None uses the font's default master.
        chars: Characters to measure. None measures every encoded glyph. Characters the font does not
            have are listed in `skipped`.
        stroke_convention: Which stroke counts to use (see fontbench2.strokes).
        font_id: How results from this font and master are identified later, e.g. in a reference.
            Defaults to "{family} {master}". Pass your own when two fonts share a family name.
        progress: Wraps the iterable being worked through (glyphs, or `chars` if given), e.g. `tqdm` for a
            progress bar.
    '''
    master = master or font.default_master
    result = FontMeasurement(
        font_id=font_id or f'{font.family} {master}',
        family=font.family,
        master=master,
        stroke_convention=stroke_convention,
    )
    wrap = progress or (lambda items: items)

    if chars is None:
        for glyph in wrap(font.glyphs(master)):
            _add(result, glyph, glyph.chars, stroke_convention)
        return result

    # dict.fromkeys drops duplicates, keeps order, and gives progress bars a length
    for char in wrap(list(dict.fromkeys(chars))):
        glyph = font.glyph_for_char(char, master)
        if glyph is not None:
            _add(result, glyph, (char,), stroke_convention)
        elif master != font.default_master and font.glyph_for_char(char) is not None:
            result.skipped[char] = SkipReason.NO_GLYPH_IN_MASTER
        else:
            result.skipped[char] = SkipReason.NOT_IN_FONT
    return result


def _add(result: FontMeasurement, glyph: Glyph, chars: tuple[str, ...], stroke_convention: Convention) -> None:
    '''Measures a glyph into `result` under each of `chars`, or records why it was skipped.'''
    frame = glyph.frame
    ink = _ink_area(glyph) if frame.area > 0 else 0.0
    reason = SkipReason.EMPTY_FRAME if frame.area <= 0 else SkipReason.NO_OUTLINE if ink == 0 else None
    for char in chars:
        if reason is None:
            result.by_char[char] = _record(glyph, char, frame, ink, stroke_convention)
        else:
            result.skipped[char] = reason


def _ink_area(glyph: Glyph) -> float:
    return abs(outline_statistics(glyph).area)


def _record(glyph: Glyph, char: str, frame: Box, ink: float, stroke_convention: Convention) -> GlyphMeasurement:
    coverage = ink / frame.area
    return GlyphMeasurement(
        char=char,
        glyph_name=glyph.name,
        advance=glyph.advance,
        coverage=coverage,
        # Ink reaching far outside the frame can push coverage past 1; it is still reported, but L* stops at 0
        lightness=lightness(min(coverage, 1.0)),
        strokes=stroke_count(char, stroke_convention),
    )
