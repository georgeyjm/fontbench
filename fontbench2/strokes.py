'''
Total stroke counts of CJK ideographs, from the Unihan database.

Two counting conventions are available:
    mainland: Simplified Chinese (zh-Hans) counts following mainland China's conventions, e.g. 过 = 6, 鬼 = 9.
        Covers the characters of Unicode 15.0 and earlier.
    irg: Unihan's current kTotalStrokes, following IRG conventions, which count 艹, 辶 and 阝 as 4, 4 and 3
        strokes, e.g. 过 = 7, 鬼 = 10. Covers every ideograph of the Unihan release it was built from.

The tables are read from a pickle built by tools/build_stroke_tables.py, which documents how they are made.
'''

import pickle
import unicodedata
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping


TABLES = Path(__file__).parent / 'data' / 'stroke_counts.pickle'

Convention = Literal['mainland', 'irg']


def stroke_count(char: str, convention: Convention = 'mainland', normalize: bool = True) -> int | None:
    '''
    Returns the total number of strokes of a CJK ideograph, or None if the table has no count for it.

    Arguments:
        char: A single character.
        convention: 'mainland' for zh-Hans counts, or 'irg' for Unihan's current counts (see module docs).
            Characters added after Unicode 15.0 only have an 'irg' count.
        normalize: If the character has no entry, look up its NFKC form instead. This covers the Kangxi Radicals
            block (e.g. ⼈ U+2F08 → 人) and two characters of CJK Radicals Supplement (⺟ and ⻳). The rest of
            CJK Radicals Supplement has no stroke count. Compatibility ideographs have their own entries.
    '''
    if len(char) != 1:
        raise ValueError(f'Expected a single character, got {char!r}.')
    table = stroke_counts(convention)
    count = table.get(char)
    if count is None and normalize:
        normalized = unicodedata.normalize('NFKC', char)
        if len(normalized) == 1 and normalized != char:
            count = table.get(normalized)
    return count


def stroke_counts(convention: Convention = 'mainland') -> Mapping[str, int]:
    '''Returns one full table as a read-only mapping from character to stroke count.'''
    tables = _tables()
    if convention not in ('mainland', 'irg'):
        raise ValueError(f"Unknown convention {convention!r}; use 'mainland' or 'irg'.")
    return tables[convention]


def stroke_table_info() -> Mapping[str, Any]:
    '''
    Describes the tables: their sources, Unicode versions, build date, and the mainland counts that were
    corrected using the 通用规范汉字表 order ({character: (Unihan count, corrected count)}).
    '''
    return _tables()['info']


@cache
def _tables() -> dict[str, Mapping]:
    with TABLES.open('rb') as f:
        tables = pickle.load(f)
    return {
        'mainland': MappingProxyType(tables['mainland']),
        'irg': MappingProxyType(tables['irg']),
        'info': MappingProxyType(tables['info']),
    }
