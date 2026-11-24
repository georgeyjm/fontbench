from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable

from fontTools.pens.basePen import AbstractPen


@dataclass(frozen=True)
class Box:
    '''
    An axis-aligned rectangle in font units, with y pointing up.
    '''
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def area(self) -> float:
        return self.width * self.height


@runtime_checkable
class Glyph(Protocol):
    '''
    One glyph in one master, from any source format.

    `draw` always sends plain contours to the pen: components are decomposed (with their transforms applied),
    so pens never need a glyph set.
    '''

    @property
    def name(self) -> str:
        '''Glyph name, e.g. 'uni4E00'.'''
        ...

    @property
    def chars(self) -> tuple[str, ...]:
        '''Every character mapped to this glyph, in codepoint order. Empty for unencoded glyphs.'''
        ...

    @property
    def char(self) -> str | None:
        '''The first character in `chars`, or None for unencoded glyphs.'''
        ...

    @property
    def master(self) -> str:
        '''Name of the master (or named instance) this glyph was taken from.'''
        ...

    @property
    def advance(self) -> float:
        '''Advance width in font units.'''
        ...

    @property
    def frame(self) -> Box:
        '''
        The box measurements are relative to: from x = 0 to the advance width, and from the descender to the
        ascender. Ink outside the frame still exists; the frame only defines the reference area.
        '''
        ...

    def draw(self, pen: AbstractPen) -> None:
        '''Draws the glyph's outline into `pen`, with components decomposed.'''
        ...


@runtime_checkable
class Font(Protocol):
    '''
    A font in any source format, giving access to its glyphs master by master.

    Methods that take `master` use `default_master` when it is None.
    '''

    @property
    def path(self) -> Path | None:
        ...

    @property
    def family(self) -> str:
        ...

    @property
    def masters(self) -> tuple[str, ...]:
        '''Names of the masters (Glyphs files) or named instances (variable fonts) that glyphs can be taken from.'''
        ...

    @property
    def default_master(self) -> str:
        ...

    @property
    def upm(self) -> int:
        ...

    def glyph(self, name: str, master: str | None = None) -> Glyph | None:
        '''The glyph with this glyph name, or None if the font (or that master) does not have it.'''
        ...

    def glyph_for_char(self, char: str, master: str | None = None) -> Glyph | None:
        '''The glyph the font maps this character to, or None if the character is not supported.'''
        ...

    def glyphs(self, master: str | None = None, encoded_only: bool = True) -> Iterator[Glyph]:
        '''All glyphs in one master, in the font's glyph order. Unencoded glyphs are skipped unless asked for.'''
        ...
