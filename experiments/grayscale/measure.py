'''
Measures the grayscale of every character in one or more fonts with fontbench2, and saves the results.

Output format is chosen by the file extension:
    .jsonl   one row per character and master: font_id, family, master, char, glyph_name, advance, coverage,
             lightness, strokes. Load with pandas.read_json(path, lines=True).
    .pickle  a list of fontbench2.FontMeasurement objects, one per font and master.

Fonts can be .glyphs files, pickled GSFont objects (.pickle/.pkl, to skip slow parsing), or compiled fonts.

    python experiments/grayscale/measure.py "glyphs/书宋.glyphs" -o experiments/grayscale/data/书宋-v2.jsonl
    python experiments/grayscale/measure.py 各种黑体大全/*.ttf --master Regular -o regular.pickle
'''

import argparse
import dataclasses
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

from tqdm import tqdm

import fontbench2 as fb


def main():
    args = parse_args()
    if args.output.exists() and not args.overwrite:
        sys.exit(f'{args.output} exists; pass --overwrite to replace it.')

    measurements = []
    for path in args.fonts:
        font = load_font(path, args.font_number)
        masters = args.master or font.masters
        for master in masters:
            if master not in font.masters:
                print(f'{path.name}: no master "{master}" (has {", ".join(font.masters)}), skipping', file=sys.stderr)
                continue
            measurements.append(measure(font, master, args.strokes))

    if args.output.suffix == '.jsonl':
        with args.output.open('w', encoding='utf-8') as f:
            for m in measurements:
                for glyph in m.by_char.values():
                    row = {'font_id': m.font_id, 'family': m.family, 'master': m.master, **dataclasses.asdict(glyph)}
                    f.write(json.dumps(row, ensure_ascii=False) + '\n')
    else:
        with args.output.open('wb') as f:
            pickle.dump(measurements, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f'Saved {len(measurements)} font masters to {args.output}')


def load_font(path: Path, font_number: int | None) -> fb.Font:
    if path.suffix.lower() in ('.pickle', '.pkl'):
        with path.open('rb') as f:
            return fb.open_font(pickle.load(f))
    return fb.open_font(path, font_number)


def measure(font: fb.Font, master: str, strokes: str) -> fb.FontMeasurement:
    font_id = f'{font.family} {master}'
    result = fb.measure_font(font, master, stroke_convention=strokes, font_id=font_id,
                             progress=lambda items: tqdm(items, desc=font_id, unit=' glyphs'))
    if result.skipped:
        reasons = ', '.join(f'{n} {reason}' for reason, n in Counter(result.skipped.values()).most_common())
        print(f'    measured {len(result.by_char)}, skipped {reasons}')
    return result


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('fonts', nargs='+', type=Path, help='Fonts to measure')
    parser.add_argument('-o', '--output', type=Path, required=True, help='Output .jsonl or .pickle file')
    parser.add_argument('-m', '--master', action='append',
                        help='Master or named instance to measure; repeat for several (default: all)')
    parser.add_argument('--strokes', choices=('mainland', 'irg'), default='mainland',
                        help='Stroke count convention (default: mainland)')
    parser.add_argument('--font-number', type=int, help='Font to open from TTC/OTC collections')
    parser.add_argument('--overwrite', action='store_true', help='Replace the output file if it exists')
    args = parser.parse_args()
    if args.output.suffix not in ('.jsonl', '.pickle', '.pkl'):
        parser.error('Output must end in .jsonl, .pickle or .pkl')
    return args


if __name__ == '__main__':
    main()
