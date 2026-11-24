from __future__ import annotations

from pathlib import Path
from typing import Iterator, Mapping

from fontTools.pens.basePen import AbstractPen, NullPen
from fontTools.pens.filterPen import DecomposingFilterPen
from fontTools.ttLib import TTFont

from fontbench.sources.base import Box


# Windows platform, Unicode encodings
_WINDOWS = 3
_WINDOWS_ENCODINGS = (1, 10)
# Windows language IDs: Chinese (PRC, Hong Kong, Taiwan, Macao), then English (US, UK)
_CHINESE_LANGUAGES = (0x0804, 0x0C04, 0x0404, 0x1404)
_ENGLISH_LANGUAGES = (0x0409, 0x0809)

_NAME_TYPOGRAPHIC_FAMILY = 16
_NAME_FAMILY = 1
_NAME_TYPOGRAPHIC_SUBFAMILY = 17
_NAME_SUBFAMILY = 2


class CompiledFont:
    '''
    A compiled font file (TTF, OTF, TTC or OTC), static or variable.

    For variable fonts, the masters are the named instances in the fvar table. Glyph outlines and advance
    widths at each instance are interpolated by fontTools.
    '''

    def __init__(self, path: str | Path, font_number: int | None = None):
        '''
        Arguments:
            path: Path to the font file.
            font_number: Which font to open from a collection (TTC/OTC).
        '''
        self._path = Path(path)
        self.ttfont = TTFont(self._path, fontNumber=-1 if font_number is None else font_number)
        for table in ('name', 'head', 'hmtx'):
            if table not in self.ttfont:
                raise ValueError(f'Font has no "{table}" table: {self._path}')

        self._is_variable = 'fvar' in self.ttfont
        # Without HVAR, fontTools only interpolates a glyph's advance width once the glyph is drawn
        self._width_needs_draw = self._is_variable and 'HVAR' not in self.ttfont and 'gvar' in self.ttfont

        cmap = self.ttfont.getBestCmap() or {}
        self._cmap = {chr(codepoint): glyph_name for codepoint, glyph_name in cmap.items()}
        chars_by_glyph: dict[str, list[str]] = {}
        for codepoint in sorted(cmap):
            chars_by_glyph.setdefault(cmap[codepoint], []).append(chr(codepoint))
        self._chars_by_glyph = {name: tuple(chars) for name, chars in chars_by_glyph.items()}

        self._locations = self._read_masters()
        self._default_master = self._find_default_master()
        self._glyph_sets: dict[str, Mapping] = {}

        if 'OS/2' in self.ttfont:
            self.ascender = self.ttfont['OS/2'].sTypoAscender
            self.descender = self.ttfont['OS/2'].sTypoDescender
        else:
            self.ascender = self.ttfont['hhea'].ascent
            self.descender = self.ttfont['hhea'].descent

    def __repr__(self) -> str:
        return f'CompiledFont({self._path.name!r}: {self.family}, masters {list(self.masters)})'

    @property
    def path(self) -> Path:
        return self._path

    @property
    def family(self) -> str:
        return self.get_name(_NAME_TYPOGRAPHIC_FAMILY, _NAME_FAMILY) or self._path.stem

    @property
    def masters(self) -> tuple[str, ...]:
        return tuple(self._locations)

    @property
    def default_master(self) -> str:
        return self._default_master

    @property
    def upm(self) -> int:
        return self.ttfont['head'].unitsPerEm

    @property
    def is_variable(self) -> bool:
        return self._is_variable

    def location(self, master: str | None = None) -> dict[str, float]:
        '''User-space axis coordinates of a master. Empty for static fonts.'''
        return dict(self._locations[self._master_name(master)])

    def get_name(self, *name_ids: int, prefer_chinese: bool = True) -> str | None:
        '''
        Returns the first name found for the given name IDs, trying each ID in order.
        Windows Unicode records are preferred, in Chinese first (unless `prefer_chinese` is False), then English.
        '''
        name_table = self.ttfont['name']
        languages = (_CHINESE_LANGUAGES + _ENGLISH_LANGUAGES) if prefer_chinese else _ENGLISH_LANGUAGES
        for name_id in name_ids:
            for language in languages:
                for encoding in _WINDOWS_ENCODINGS:
                    record = name_table.getName(name_id, _WINDOWS, encoding, language)
                    if record is not None:
                        return record.toUnicode()
            fallback = name_table.getDebugName(name_id)
            if fallback:
                return fallback
        return None

    def glyph(self, name: str, master: str | None = None) -> CompiledGlyph | None:
        master = self._master_name(master)
        glyph_set = self._glyph_set(master)
        if name not in glyph_set:
            return None
        return CompiledGlyph(self, name, master, glyph_set)

    def glyph_for_char(self, char: str, master: str | None = None) -> CompiledGlyph | None:
        name = self._cmap.get(char)
        return None if name is None else self.glyph(name, master)

    def glyphs(self, master: str | None = None, encoded_only: bool = True) -> Iterator[CompiledGlyph]:
        master = self._master_name(master)
        glyph_set = self._glyph_set(master)
        for name in self.ttfont.getGlyphOrder():
            if encoded_only and name not in self._chars_by_glyph:
                continue
            yield CompiledGlyph(self, name, master, glyph_set)

    def _read_masters(self) -> dict[str, dict[str, float]]:
        subfamily = self.get_name(_NAME_TYPOGRAPHIC_SUBFAMILY, _NAME_SUBFAMILY) or 'Regular'
        if not self._is_variable:
            return {subfamily: {}}
        locations = {}
        for instance in self.ttfont['fvar'].instances:
            name = self.get_name(instance.subfamilyNameID) or str(instance.coordinates)
            # Keep the first instance when several share a name
            locations.setdefault(name, dict(instance.coordinates))
        if not locations:
            # Variable font without named instances: offer the default location only
            locations[subfamily] = {axis.axisTag: axis.defaultValue for axis in self.ttfont['fvar'].axes}
        return locations

    def _find_default_master(self) -> str:
        if self._is_variable:
            defaults = {axis.axisTag: axis.defaultValue for axis in self.ttfont['fvar'].axes}
            for name, location in self._locations.items():
                if location == defaults:
                    return name
        return next(iter(self._locations))

    def _master_name(self, master: str | None) -> str:
        if master is None:
            return self._default_master
        if master not in self._locations:
            raise KeyError(f'Master "{master}" not found. Available masters: {list(self._locations)}')
        return master

    def _glyph_set(self, master: str) -> Mapping:
        if master not in self._glyph_sets:
            location = self._locations[master] or None
            self._glyph_sets[master] = self.ttfont.getGlyphSet(location=location)
        return self._glyph_sets[master]


class CompiledGlyph:
    '''
    A glyph from a compiled font at one master. Created by CompiledFont, not directly.
    '''

    def __init__(self, font: CompiledFont, name: str, master: str, glyph_set: Mapping):
        self.font = font
        self._name = name
        self._master = master
        self._glyph_set = glyph_set
        self._tt_glyph = glyph_set[name]
        self._width_ready = not font._width_needs_draw

    def __repr__(self) -> str:
        return f'CompiledGlyph({self._name!r}, {self.char!r}, {self._master!r})'

    @property
    def name(self) -> str:
        return self._name

    @property
    def chars(self) -> tuple[str, ...]:
        return self.font._chars_by_glyph.get(self._name, ())

    @property
    def char(self) -> str | None:
        chars = self.chars
        return chars[0] if chars else None

    @property
    def master(self) -> str:
        return self._master

    @property
    def advance(self) -> float:
        if not self._width_ready:
            self._tt_glyph.draw(NullPen())
            self._width_ready = True
        return self._tt_glyph.width

    @property
    def frame(self) -> Box:
        return Box(0, self.font.descender, self.advance, self.font.ascender)

    def draw(self, pen: AbstractPen) -> None:
        self._tt_glyph.draw(DecomposingFilterPen(pen, self._glyph_set, reverseFlipped=True))
        self._width_ready = True
