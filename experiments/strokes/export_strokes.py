'''
Exports the total stroke count of every character in a character set, as CSV or XLSX.

The character set is a named set or a text file:
    9169             the 9169 set (fontbench/sets/9169.txt)
    tgh              通用规范汉字表, all three levels
    tgh1, tgh2, ...  通用规范汉字表 levels; digits combine levels, e.g. tgh12 = levels 1 and 2
    <path>           a UTF-8 text file; every non-whitespace character counts, lines starting with # are skipped

    python experiments/strokes/export_strokes.py 9169
    python experiments/strokes/export_strokes.py tgh1 -o output/strokes/tgh1.xlsx
    python experiments/strokes/export_strokes.py my_chars.txt --format xlsx --convention mainland

Rows are in code point order, with one column per stroke-count convention (see fontbench.strokes). Characters
without a count are left blank. By default writes output/strokes/<charset>.csv.
'''

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

import fontbench as fb


REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / 'output' / 'strokes'
CONVENTIONS = ('mainland', 'irg')
FORMATS = ('csv', 'xlsx')


def main():
    args = parse_args()
    chars, name = load_charset(args.charset)
    conventions = CONVENTIONS if args.convention == 'both' else (args.convention,)

    path, fmt = output_path(args, name)
    if fmt == 'xlsx':
        try:
            import openpyxl  # noqa: F401  (pandas writes .xlsx through it)
        except ImportError:
            sys.exit('Writing .xlsx needs openpyxl, which is not installed: uv add --optional dev openpyxl')
    table = stroke_table(chars, conventions)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == 'csv':
        # utf-8-sig so Excel opens the CSV as UTF-8 instead of guessing a legacy encoding.
        table.to_csv(path, index=False, encoding='utf-8-sig')
    else:
        table.to_excel(path, index=False, sheet_name=name[:31])

    missing = {c: int(table[f'strokes_{c}'].isna().sum()) for c in conventions}
    summary = ', '.join(f'{n} have no {c} count' for c, n in missing.items() if n)
    print(f'Wrote {len(table)} characters to {path}' + (f' ({summary})' if summary else ''))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('charset', help="'9169', 'tgh', 'tgh1'..'tgh123', or a text file of characters")
    parser.add_argument('-o', '--output', type=Path,
                        help='output file; its extension (.csv or .xlsx) sets the format unless --format is given')
    parser.add_argument('-f', '--format', choices=FORMATS, help='output format (default: from -o, else csv)')
    parser.add_argument('-c', '--convention', choices=(*CONVENTIONS, 'both'), default='both',
                        help='stroke-count convention (default: both, one column each)')
    return parser.parse_args()


def load_charset(spec: str) -> tuple[list[str], str]:
    '''Returns the characters in code point order, and a name for the set (used for file and sheet names).'''
    if spec == '9169':
        return sorted(fb.chars_9169()), '9169'
    if match := re.fullmatch(r'tgh([123]*)', spec):
        levels = sorted({int(d) for d in match[1]}) or [1, 2, 3]
        return sorted(fb.tongyong_guifan(*levels)), 'tgh' + ''.join(map(str, levels))

    path = Path(spec)
    if not path.is_file():
        sys.exit(f"Unknown character set {spec!r}: not '9169', 'tgh[123]' or an existing file.")
    text = '\n'.join(line for line in path.read_text(encoding='utf-8-sig').splitlines()
                     if not line.startswith('#'))
    chars = sorted({c for c in text if not c.isspace()})
    if not chars:
        sys.exit(f'{path} has no characters.')
    return chars, path.stem


def output_path(args: argparse.Namespace, name: str) -> tuple[Path, str]:
    if args.output is None:
        fmt = args.format or 'csv'
        return OUTPUT / f'{name}.{fmt}', fmt
    suffix = args.output.suffix.lower().lstrip('.')
    fmt = args.format or (suffix if suffix in FORMATS else None)
    if fmt is None:
        sys.exit(f'Cannot tell the format from {args.output}; use a .csv or .xlsx name, or --format.')
    if suffix != fmt:
        return args.output.with_name(args.output.name + f'.{fmt}'), fmt
    return args.output, fmt


def stroke_table(chars: list[str], conventions: tuple[str, ...]) -> pd.DataFrame:
    rows = []
    for char in chars:
        row = {'char': char, 'unicode': f'U+{ord(char):04X}'}
        for convention in conventions:
            row[f'strokes_{convention}'] = fb.stroke_count(char, convention)
        rows.append(row)
    table = pd.DataFrame(rows)
    # Nullable ints, so a missing count is a blank cell rather than turning the column into floats.
    for convention in conventions:
        table[f'strokes_{convention}'] = table[f'strokes_{convention}'].astype('Int64')
    return table


if __name__ == '__main__':
    main()
