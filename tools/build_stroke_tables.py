'''
Builds fontbench's character tables from the Unihan database and saves them as a pickle.

Three tables are built:

mainland: Stroke counts for simplified Chinese (zh-Hans), following mainland China's counting conventions.
    Taken from kTotalStrokes in Unihan 15.0, the last release where that property gave zh-Hans counts
    (the first of its values); from 15.1 on it follows IRG conventions instead. The 8,105 characters of the
    通用规范汉字表 are then checked against that table's official order, which is sorted by stroke count within
    each of its three levels (positions from the kTGH property). Where the Unihan 15.0 count breaks the order,
    it is replaced by the smallest count the order allows. These are simplified forms (e.g. 䴓 with 鸟) that
    Unihan 15.0 counted with traditional components. Characters added after Unicode 15.0 are not included.

irg: kTotalStrokes from the given (normally the latest) Unihan release, following IRG conventions.
    Differs from mainland counts for components like 艹, 辶 and 阝 (e.g. 过: 7 here, 6 in mainland).

tgh: Each character's position (1-8105) in the 通用规范汉字表, from kTGH in the latest release.
    Positions 1-3500 are level 1, 3501-6500 level 2, and 6501-8105 level 3.

By default both Unihan releases are downloaded from unicode.org. Pass local Unihan.zip files to skip that.

    python tools/build_stroke_tables.py
    python tools/build_stroke_tables.py --unihan-15 Unihan-15.zip --unihan-latest Unihan.zip
'''

import argparse
import io
import pickle
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


UNIHAN_15_URL = 'https://www.unicode.org/Public/15.0.0/ucd/Unihan.zip'
UNIHAN_LATEST_URL = 'https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip'
OUTPUT = Path(__file__).resolve().parent.parent / 'fontbench' / 'data' / 'stroke_counts.pickle'
# Ranges of kTGH positions for the three levels of the 通用规范汉字表; each level is sorted by stroke count
TGH_LEVELS = ((1, 3500), (3501, 6500), (6501, 8105))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--unihan-15', type=Path, help='Local Unihan.zip of Unicode 15.0.0 (downloaded if omitted)')
    parser.add_argument('--unihan-latest', type=Path, help='Local Unihan.zip of the latest release (downloaded if omitted)')
    parser.add_argument('-o', '--output', type=Path, default=OUTPUT, help='Where to write the pickle')
    args = parser.parse_args()

    unihan_15 = open_unihan(args.unihan_15, UNIHAN_15_URL)
    unihan_latest = open_unihan(args.unihan_latest, UNIHAN_LATEST_URL)

    zh_hans, version_15 = read_field(unihan_15, 'kTotalStrokes')
    irg, version_latest = read_field(unihan_latest, 'kTotalStrokes')
    tgh, _ = read_field(unihan_latest, 'kTGH')
    if version_15 != '15.0.0':
        raise SystemExit(f'Expected Unihan 15.0.0 for mainland counts, got {version_15}')

    mainland = {char: int(value.split()[0]) for char, value in zh_hans.items()}
    irg = {char: int(value.split()[0]) for char, value in irg.items()}
    # kTGH values look like '2013:1234'; the number is the character's position in the table
    positions = {char: int(value.split()[0].split(':')[1]) for char, value in tgh.items()}
    corrections = correct_by_order(mainland, positions)
    # Checked after correct_by_order, which relies on the same assumption
    if sorted(positions.values()) != list(range(1, TGH_LEVELS[-1][1] + 1)):
        raise SystemExit('kTGH positions are not exactly 1-8105')

    tables = {
        'mainland': mainland,
        'irg': irg,
        'tgh': positions,
        'info': {
            'mainland_source': f'Unihan {version_15} kTotalStrokes (zh-Hans), corrected by the 通用规范汉字表 order',
            'irg_source': f'Unihan {version_latest} kTotalStrokes',
            'tgh_source': f'Unihan {version_latest} kTGH (通用规范汉字表, 2013)',
            'unicode_versions': {'mainland': version_15, 'irg': version_latest},
            'corrections': corrections,
            'built': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'license': 'Unicode data © Unicode, Inc. See https://www.unicode.org/terms_of_use.html',
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('wb') as f:
        pickle.dump(tables, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f'mainland: {len(mainland)} characters (Unihan {version_15}), {len(corrections)} corrected by order:')
    for char, (old, new) in corrections.items():
        print(f'    {char} U+{ord(char):04X}: {old} → {new}')
    print(f'irg: {len(irg)} characters (Unihan {version_latest})')
    print(f'tgh: {len(positions)} characters')
    print(f'Saved to {args.output}')


def open_unihan(path: Path | None, url: str) -> zipfile.ZipFile:
    if path is not None:
        return zipfile.ZipFile(path)
    print(f'Downloading {url}...')
    with urllib.request.urlopen(url) as response:
        return zipfile.ZipFile(io.BytesIO(response.read()))


def read_field(unihan: zipfile.ZipFile, field: str) -> tuple[dict[str, str], str | None]:
    '''
    Returns {character: raw value} for one Unihan field, searching every file in the archive,
    and the Unicode version stated in the file headers.
    '''
    values, version = {}, None
    for name in unihan.namelist():
        if not name.endswith('.txt'):
            continue
        with unihan.open(name) as f:
            for line in io.TextIOWrapper(f, encoding='utf-8'):
                if line.startswith('#'):
                    lowered = line.lower()
                    if version is None and lowered.startswith('# unicode version'):
                        version = line.split()[-1]
                    continue
                parts = line.rstrip('\n').split('\t')
                if len(parts) == 3 and parts[1] == field:
                    values[chr(int(parts[0][2:], 16))] = parts[2]
    if not values:
        raise SystemExit(f'No {field} entries found in the Unihan archive')
    return values, version


def correct_by_order(counts: dict[str, int], positions: dict[str, int]) -> dict[str, tuple[int, int]]:
    '''
    Makes counts nondecreasing along each level of the 通用规范汉字表, changing as few as possible.
    Where several counts would be equally good, the smallest is used. Edits `counts` in place and
    returns {character: (old count, new count)} for every change.
    '''
    corrections = {}
    for low, high in TGH_LEVELS:
        chars = sorted((c for c, p in positions.items() if low <= p <= high), key=positions.get)
        fitted = _fit_nondecreasing([counts[c] for c in chars])
        for char, new in zip(chars, fitted):
            if counts[char] != new:
                corrections[char] = (counts[char], new)
                counts[char] = new
    return corrections


def _fit_nondecreasing(values: list[int]) -> list[int]:
    '''
    The nondecreasing integer sequence that differs from `values` in the fewest places,
    preferring smaller values on ties.
    '''
    candidates = range(1, max(values) + 1)
    # cost[i][v]: fewest mismatches for values[i:] given values[i] >= v ... computed backwards
    n = len(values)
    INF = n + 1
    suffix = [[0] * (len(candidates) + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        best = INF
        for k in range(len(candidates) - 1, -1, -1):
            # Best cost when values[i] is at least candidates[k]
            cost_here = (values[i] != candidates[k]) + suffix[i + 1][k]
            best = min(best, cost_here)
            suffix[i][k] = best
        suffix[i][len(candidates)] = INF
    # Walk forwards, choosing the smallest value that keeps the optimal cost
    fitted, k = [], 0
    for i in range(n):
        target = suffix[i][k]
        while (values[i] != candidates[k]) + suffix[i + 1][k] != target:
            k += 1
        fitted.append(candidates[k])
    return fitted


if __name__ == '__main__':
    main()
