from __future__ import annotations

from pathlib import Path
from typing import Iterator, Mapping

from fontTools.pens.basePen import AbstractPen
from fontTools.pens.filterPen import DecomposingFilterPen
from glyphsLib import GSFont, GSFontMaster, GSGlyph, GSLayer

from fontbench2.sources.base import Box


class GlyphsFont:
    '''
    A Glyphs source file. The masters are the file's font masters; only master layers are used
    (brace and bracket layers are ignored).
    '''

    def __init__(self, source: str | Path | GSFont):
        '''
        Arguments:
            source: Path to a .glyphs file, or an already parsed GSFont (e.g. one loaded from a cache).
        '''
        if isinstance(source, GSFont):
            self.gsfont = source
            filepath = getattr(source, 'filepath', None)
            self._path = Path(filepath) if filepath else None
        else:
            self._path = Path(source)
            self.gsfont = GSFont(str(self._path))

        self._masters: dict[str, GSFontMaster] = {}
        for master in self.gsfont.masters:
            # Keep the first master when several share a name
            self._masters.setdefault(master.name, master)

        self._glyphs_by_name: dict[str, GSGlyph] = {}
        self._cmap: dict[str, str] = {}
        for glyph in self.gsfont.glyphs:
            self._glyphs_by_name.setdefault(glyph.name, glyph)
            for char in _glyph_chars(glyph):
                self._cmap.setdefault(char, glyph.name)

        self._glyph_sets: dict[str, _MasterGlyphSet] = {}

    def __repr__(self) -> str:
        name = self._path.name if self._path else 'unsaved'
        return f'GlyphsFont({name!r}: {self.family}, masters {list(self.masters)})'

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def family(self) -> str:
        return self.gsfont.familyName

    @property
    def masters(self) -> tuple[str, ...]:
        return tuple(self._masters)

    @property
    def default_master(self) -> str:
        return next(iter(self._masters))

    @property
    def upm(self) -> int:
        return self.gsfont.upm

    def glyph(self, name: str, master: str | None = None) -> GlyphsGlyph | None:
        gsglyph = self._glyphs_by_name.get(name)
        if gsglyph is None:
            return None
        return self._make_glyph(gsglyph, self._master(master))

    def glyph_for_char(self, char: str, master: str | None = None) -> GlyphsGlyph | None:
        name = self._cmap.get(char)
        return None if name is None else self.glyph(name, master)

    def glyphs(self, master: str | None = None, encoded_only: bool = True) -> Iterator[GlyphsGlyph]:
        gsmaster = self._master(master)
        for gsglyph in self.gsfont.glyphs:
            if encoded_only and not gsglyph.unicodes:
                continue
            glyph = self._make_glyph(gsglyph, gsmaster)
            if glyph is not None:
                yield glyph

    def _master(self, master: str | None) -> GSFontMaster:
        if master is None:
            return self._masters[self.default_master]
        if master not in self._masters:
            raise KeyError(f'Master "{master}" not found. Available masters: {list(self._masters)}')
        return self._masters[master]

    def _make_glyph(self, gsglyph: GSGlyph, gsmaster: GSFontMaster) -> GlyphsGlyph | None:
        layer = gsglyph.layers[gsmaster.id]
        if layer is None:
            return None
        if gsmaster.id not in self._glyph_sets:
            self._glyph_sets[gsmaster.id] = _MasterGlyphSet(self._glyphs_by_name, gsmaster.id)
        return GlyphsGlyph(gsglyph, layer, gsmaster, self._glyph_sets[gsmaster.id])


class GlyphsGlyph:
    '''
    A glyph from a Glyphs source at one master. Created by GlyphsFont, not directly.
    '''

    def __init__(self, gsglyph: GSGlyph, layer: GSLayer, gsmaster: GSFontMaster, glyph_set: Mapping):
        self.gsglyph = gsglyph
        self.layer = layer
        self._gsmaster = gsmaster
        self._glyph_set = glyph_set

    def __repr__(self) -> str:
        return f'GlyphsGlyph({self.name!r}, {self.char!r}, {self.master!r})'

    @property
    def name(self) -> str:
        return self.gsglyph.name

    @property
    def chars(self) -> tuple[str, ...]:
        return _glyph_chars(self.gsglyph)

    @property
    def char(self) -> str | None:
        chars = self.chars
        return chars[0] if chars else None

    @property
    def master(self) -> str:
        return self._gsmaster.name

    @property
    def advance(self) -> float:
        return self.layer.width

    @property
    def frame(self) -> Box:
        return Box(0, self._gsmaster.descender, self.layer.width, self._gsmaster.ascender)

    def draw(self, pen: AbstractPen) -> None:
        self.layer.draw(DecomposingFilterPen(pen, self._glyph_set, reverseFlipped=True))


class _MasterGlyphSet(Mapping):
    '''
    Resolves component names to the layers of one master, so components can be decomposed.
    '''

    def __init__(self, glyphs_by_name: dict[str, GSGlyph], master_id: str):
        self._glyphs_by_name = glyphs_by_name
        self._master_id = master_id

    def __getitem__(self, name: str) -> GSLayer:
        gsglyph = self._glyphs_by_name.get(name)
        layer = None if gsglyph is None else gsglyph.layers[self._master_id]
        if layer is None:
            raise KeyError(name)
        return layer

    def __iter__(self):
        return iter(self._glyphs_by_name)

    def __len__(self) -> int:
        return len(self._glyphs_by_name)


def _glyph_chars(gsglyph: GSGlyph) -> tuple[str, ...]:
    return tuple(sorted(chr(int(code, 16)) for code in gsglyph.unicodes or ()))
