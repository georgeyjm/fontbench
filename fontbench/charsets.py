'''
Standard character sets, for choosing which characters to normalize or compare over.

The 通用规范汉字表 (Table of General Standard Chinese Characters, 2013) has 8,105 characters in three levels:
    1: 3,500 common characters
    2: 3,000 further characters in general use
    3: 1,605 characters for names, places, science and classical texts
Positions come from Unihan's kTGH property (see tools/build_stroke_tables.py).

The 9169 set is the character set Chinese fonts are commonly designed for: all of GB 2312, most of the
通用规范汉字表 (levels 1 and 2 nearly complete, a fifth of level 3) and about 2,300 traditional forms. Its list is
kept in sets/9169.txt, which documents where it comes from.
'''

from functools import cache
from pathlib import Path

from fontbench.strokes import _tables


SETS = Path(__file__).parent / 'sets'

TONGYONG_GUIFAN_LEVELS = {1: (1, 3500), 2: (3501, 6500), 3: (6501, 8105)}


def tongyong_guifan(*levels: int) -> frozenset[str]:
    '''
    Characters of the 通用规范汉字表 in the given levels; level 1 (the 3,500 common characters) by default.
    '''
    levels = levels or (1,)
    unknown = set(levels) - set(TONGYONG_GUIFAN_LEVELS)
    if unknown:
        raise ValueError(f'Unknown levels {sorted(unknown)}; the table has levels 1, 2 and 3.')
    return frozenset().union(*(_level_chars(level) for level in levels))


def tongyong_guifan_level(char: str) -> int | None:
    '''The character's level in the 通用规范汉字表, or None if it is not in the table.'''
    position = _tables()['tgh'].get(char)
    if position is None:
        return None
    return next(level for level, (low, high) in TONGYONG_GUIFAN_LEVELS.items() if low <= position <= high)


@cache
def chars_9169() -> frozenset[str]:
    '''
    The 9169 characters commonly designed in Chinese fonts, as CJK unified ideographs. Fonts often also map Kangxi
    radicals or compatibility ideographs to the same glyphs; those code points are not part of the set.
    '''
    with (SETS / '9169.txt').open(encoding='utf-8') as f:
        chars = frozenset(line.strip() for line in f if line.strip() and not line.startswith('#'))
    assert len(chars) == 9169, len(chars)
    return chars


@cache
def _level_chars(level: int) -> frozenset[str]:
    low, high = TONGYONG_GUIFAN_LEVELS[level]
    return frozenset(char for char, position in _tables()['tgh'].items() if low <= position <= high)
