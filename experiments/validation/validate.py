'''
Validates reference grayscale on the 黑体 corpus (see corpus.py). A target font is only ever compared with
references from other design families.

    python experiments/validation/validate.py
    python experiments/validation/validate.py --sections 4 --normalization robust_z --model "spline k5"

Sections:
    1  corpus       each font's overall darkness and distribution shape
    2  agreement    how closely a font's normalized values follow the reference positions, per normalization
    3  prediction   held-out prediction error per normalization and tone-curve model, on four splits
    4  references   how prediction depends on which and how many reference fonts are used

Tables are printed and saved as CSV in output/validation/ (gitignored). Prediction errors are relative to the
target's median coverage over level 1, so fonts of different weights are comparable: 2% means an error of 0.02 ×
the coverage of the font's typical glyph.
'''

from __future__ import annotations

import argparse
import random
import time
from typing import Callable, Iterable

import numpy as np
import pandas as pd

import fontbench as fb
from corpus import REPO, CorpusFont, load_corpus, reference_fonts


OUTPUT = REPO / 'output' / 'validation'
NORMALIZATIONS = ('normal_score', 'robust_z', 'ratio')
MODELS = {
    'linear': dict(model='linear'),
    'spline k3': dict(model='spline', knots=3),
    'spline k5': dict(model='spline', knots=5),
    'spline k7': dict(model='spline', knots=7),
    'spline k5 smooth': dict(model='spline', knots=5, smoothing=0.1),
}
LEVEL_1 = fb.tongyong_guifan(1)
LEVELS_2_3 = fb.tongyong_guifan(2, 3)
SET_9169 = fb.chars_9169()
SPLITS = ('L1 → L2–3', '3000 → rest of 9169', 'dark 10%', 'light 10%')


def main():
    args = parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pd.set_option('display.width', 200)
    pd.set_option('display.max_columns', 20)
    corpus = load_corpus()
    print(f'{len(corpus)} SC font masters in {len({f.group for f in corpus})} design families\n')

    if 1 in args.sections:
        section_corpus(corpus)
    if 2 in args.sections or 3 in args.sections:
        section_agreement_and_prediction(corpus, args)
    if 4 in args.sections:
        section_references(corpus, args)


# 1. Corpus

def section_corpus(corpus: list[CorpusFont]):
    rows = [dict(font_id=f.font_id, group=f.group, glyphs=len(f.measurement), median=f.shape.median,
                 relative_spread=f.shape.relative_spread, skew=f.shape.skew) for f in corpus]
    df = pd.DataFrame(rows).sort_values('median')
    save(df, '1-corpus')
    heading('1. Corpus: darkness (median coverage over level 1) and shape')
    print(df.to_string(index=False, float_format='{:.3f}'.format))
    print(f'\nCorrelation of darkness with relative spread: {df["median"].corr(df.relative_spread):+.2f}, '
          f'with skew: {df["median"].corr(df["skew"]):+.2f}')


# 2 and 3. Agreement between fonts and held-out prediction

def section_agreement_and_prediction(corpus: list[CorpusFont], args):
    targets = select_targets(corpus, args.targets)
    agreement, prediction = [], []
    started = time.time()
    for i, target in enumerate(targets):
        refs = reference_fonts(target, corpus, max_darkness_ratio=None)
        splits = None
        for normalization in NORMALIZATIONS:
            reference = build(refs, normalization)
            agreement.append(dict(font_id=target.font_id, normalization=normalization,
                                  **agreement_scores(target, reference)))
            if splits is None:  # Tails are defined by the first (normal_score) reference ordering
                splits = make_splits(target, reference.positions(), random.Random(target.font_id))
            if 3 not in args.sections:
                continue
            for model, options in MODELS.items():
                for split, (train, test) in splits.items():
                    scores = evaluate(target, reference, train, test, options)
                    if scores:
                        prediction.append(dict(font_id=target.font_id, darkness=target.shape.median,
                                               normalization=normalization, model=model, split=split, **scores))
        print(f'  [{i + 1}/{len(targets)}] {target.font_id}: {len(refs)} references ({time.time() - started:.0f}s)')

    if 2 in args.sections:
        df = pd.DataFrame(agreement)
        save(df, '2-agreement')
        heading('2. Agreement: robust SD of (font − reference position) / robust SD of positions, median over fonts')
        print('Lower is better: how far one font strays from the consensus, relative to the range of positions.\n')
        table = df.groupby('normalization')[['overall', 'light 10%', 'middle 80%', 'dark 10%']].median()
        print(table.loc[list(NORMALIZATIONS)].to_string(float_format='{:.3f}'.format))

    if 3 in args.sections:
        df = pd.DataFrame(prediction)
        save(df, '3-prediction')
        heading('3. Prediction: mean absolute error on held-out glyphs, % of median coverage (median over fonts)')
        for normalization in NORMALIZATIONS:
            subset = df[df.normalization == normalization]
            table = subset.pivot_table(index='model', columns='split', values='rel_mae', aggfunc='median')
            print(f'\n{normalization}')
            print(percent(table.reindex(columns=SPLITS).loc[list(MODELS)]))
        heading('3b. Bias (predicted − actual, % of median coverage), normal_score')
        subset = df[df.normalization == 'normal_score']
        table = subset.pivot_table(index='model', columns='split', values='rel_bias', aggfunc='median')
        print(percent(table.reindex(columns=SPLITS).loc[list(MODELS)]))
        heading('3c. L1 → L2–3 error by darkness tercile, normal_score')
        subset = df[(df.normalization == 'normal_score') & (df.split == SPLITS[0])].copy()
        subset['tercile'] = pd.qcut(subset.darkness, 3, labels=['light', 'middle', 'dark'])
        table = subset.pivot_table(index='model', columns='tercile', values='rel_mae', aggfunc='median', observed=True)
        print(percent(table.loc[list(MODELS)]))
        heading('3d. Fonts the best model predicts worst (L1 → L2–3, normal_score)')
        best = subset.groupby('model').rel_mae.median().idxmin()
        worst = subset[subset.model == best].nlargest(8, 'rel_mae')[['font_id', 'darkness', 'rel_mae', 'rel_bias']]
        print(f'model: {best}')
        print(worst.to_string(index=False, formatters={'rel_mae': '{:.2%}'.format, 'rel_bias': '{:+.2%}'.format,
                                                      'darkness': '{:.3f}'.format}))


def agreement_scores(target: CorpusFont, reference: fb.Reference) -> dict[str, float]:
    values = fb.normalize(target.measurement, reference.settings.normalization)
    chars = sorted(values.keys() & reference.by_char.keys(), key=lambda c: reference.by_char[c].position)
    positions = np.array([reference.by_char[c].position for c in chars])
    differences = np.array([values[c] for c in chars]) - positions
    scale = robust_sd(positions)
    n = len(chars) // 10
    return {
        'overall': robust_sd(differences) / scale,
        'light 10%': robust_sd(differences[:n]) / scale,
        'middle 80%': robust_sd(differences[n:-n]) / scale,
        'dark 10%': robust_sd(differences[-n:]) / scale,
    }


def make_splits(target: CorpusFont, positions: dict[str, float], rng: random.Random) -> dict[str, tuple[set, set]]:
    '''Train and test characters for each split the target supports.'''
    chars = target.measurement.by_char.keys()
    splits = {SPLITS[0]: (set(LEVEL_1), set(LEVELS_2_3))}
    available = sorted(SET_9169 & chars)
    if len(available) >= 0.95 * len(SET_9169):
        train = set(rng.sample(available, 3000))
        splits[SPLITS[1]] = (train, set(available) - train)
    ordered = sorted(chars & positions.keys(), key=positions.get)
    n = len(ordered) // 10
    splits[SPLITS[2]] = (set(ordered[:-n]), set(ordered[-n:]))
    splits[SPLITS[3]] = (set(ordered[n:]), set(ordered[:n]))
    return splits


def evaluate(target: CorpusFont, reference: fb.Reference, train: Iterable[str], test: Iterable[str],
             options: dict) -> dict[str, float] | None:
    '''Relative errors of a held-out fit, or None if the split leaves too few glyphs.'''
    try:
        result = fb.evaluate_fit(target.measurement, reference, train, test, **options)
    except ValueError:
        return None
    darkness = target.shape.median
    return dict(n_train=result.n_train, n_test=result.n_test, rel_mae=result.mean_abs_error / darkness,
                rel_bias=result.bias / darkness, rel_rmse=result.rmse / darkness,
                rel_max=result.max_abs_error / darkness)


# 4. Reference choice

def section_references(corpus: list[CorpusFont], args):
    options = MODELS[args.model]
    normalization = args.normalization
    targets = one_per_group(corpus)
    print(f'\nSection 4 uses one master per family ({len(targets)} targets), {normalization} and {args.model}.')

    # 4a. Which masters
    modes: dict[str, Callable[[CorpusFont], list[CorpusFont]]] = {
        'matched (closest weight per family)': lambda t: reference_fonts(t, corpus, max_darkness_ratio=None),
        'matched, within 1.25× darkness': lambda t: reference_fonts(t, corpus, max_darkness_ratio=1.25),
        'all masters of other families': lambda t: reference_fonts(t, corpus, mode='all', max_darkness_ratio=None),
    }
    rows = []
    for target in targets:
        splits = None
        for mode, choose in modes.items():
            refs = choose(target)
            if len(refs) < 3:
                continue
            reference = build(refs, normalization)
            if splits is None:
                splits = make_splits(target, reference.positions(), random.Random(target.font_id))
            for split, (train, test) in splits.items():
                scores = evaluate(target, reference, train, test, options)
                if scores:
                    rows.append(dict(font_id=target.font_id, mode=mode, n_refs=len(refs), split=split, **scores))
    df = pd.DataFrame(rows)
    save(df, '4a-modes')
    heading('4a. Which reference masters: mean absolute error, % of median coverage (median over fonts)')
    table = df.pivot_table(index='mode', columns='split', values='rel_mae', aggfunc='median')
    table = percent(table.reindex(columns=SPLITS).loc[list(modes)])
    table['references'] = df.groupby('mode').n_refs.mean().loc[list(modes)].round(1)
    print(table)

    # 4b. How many families
    rng = random.Random(0)
    sizes = (1, 2, 4, 8, 16)
    rows = []
    for target in targets:
        refs = reference_fonts(target, corpus, max_darkness_ratio=None)
        test_splits = None
        for size in sizes + (len(refs),):
            for repeat in range(args.repeats if size < len(refs) else 1):
                sample = rng.sample(refs, min(size, len(refs)))
                reference = build(sample, normalization)
                if test_splits is None:
                    test_splits = make_splits(target, build(refs, normalization).positions(),
                                              random.Random(target.font_id))
                for split in (SPLITS[0], SPLITS[2]):
                    train, test = test_splits[split]
                    scores = evaluate(target, reference, train, test, options)
                    if not scores:
                        continue
                    rows.append(dict(font_id=target.font_id, n_refs=size if size < len(refs) else 'all',
                                     split=split, **scores))
    df = pd.DataFrame(rows)
    save(df, '4b-count')
    heading('4b. How many reference families: mean absolute error, % of median coverage (median over fonts)')
    table = df.pivot_table(index='n_refs', columns='split', values='rel_mae', aggfunc='median')
    print(percent(table.loc[list(sizes) + ['all']]))

    # 4c. Split-half reliability of the positions themselves
    rows = []
    darkness = float(np.median([f.shape.median for f in corpus]))
    pool = one_per_group(corpus, darkness)
    for repeat in range(10):
        shuffled = rng.sample(pool, len(pool))
        half = len(pool) // 2
        a, b = build(shuffled[:half], normalization), build(shuffled[half:], normalization)
        chars = sorted(a.by_char.keys() & b.by_char.keys() & LEVEL_1)
        pa = np.array([a.by_char[c].position for c in chars])
        pb = np.array([b.by_char[c].position for c in chars])
        spread = np.median([a.by_char[c].spread for c in chars])
        rows.append(dict(repeat=repeat, fonts_per_half=half, correlation=np.corrcoef(pa, pb)[0, 1],
                         rank_correlation=np.corrcoef(pa.argsort().argsort(), pb.argsort().argsort())[0, 1],
                         difference_sd=robust_sd(pa - pb), position_sd=robust_sd(pa), font_spread=spread))
    df = pd.DataFrame(rows)
    save(df, '4c-split-half')
    heading('4c. Split-half reliability: two references from disjoint halves of the families (level 1 characters)')
    print(df.drop(columns='repeat').mean().to_string(float_format='{:.3f}'.format))
    print('\ndifference_sd / √2 is the noise in one half’s positions; font_spread is one font’s typical disagreement.')


# Helpers

def build(fonts: list[CorpusFont], normalization: str) -> fb.Reference:
    settings = fb.ReferenceSettings(normalization=normalization)
    return fb.build_reference([f.measurement for f in fonts], settings)


def select_targets(corpus: list[CorpusFont], limit: int | None) -> list[CorpusFont]:
    if limit is None or limit >= len(corpus):
        return corpus
    return random.Random(0).sample(corpus, limit)


def one_per_group(corpus: list[CorpusFont], darkness: float | None = None) -> list[CorpusFont]:
    '''From each family, the master closest to `darkness` (default: the corpus median).'''
    if darkness is None:
        darkness = float(np.median([f.shape.median for f in corpus]))
    by_group: dict[str, CorpusFont] = {}
    for f in corpus:
        best = by_group.get(f.group)
        if best is None or abs(np.log(f.shape.median / darkness)) < abs(np.log(best.shape.median / darkness)):
            by_group[f.group] = f
    return list(by_group.values())


def robust_sd(values: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def percent(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(lambda v: f'{v:.2%}' if pd.notna(v) else '')


def heading(text: str):
    print(f'\n{text}\n{"─" * len(text)}')


def save(df: pd.DataFrame, name: str):
    df.to_csv(OUTPUT / f'{name}.csv', index=False)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sections', type=int, nargs='+', default=[1, 2, 3, 4], choices=[1, 2, 3, 4])
    parser.add_argument('--targets', type=int, help='Use a random sample of this many target fonts in sections 2–3')
    parser.add_argument('--model', default='spline k5', choices=list(MODELS), help='Tone curve model for section 4')
    parser.add_argument('--normalization', default='robust_z', choices=NORMALIZATIONS,
                        help='Normalization for section 4')
    parser.add_argument('--repeats', type=int, default=3, help='Random reference samples per size in section 4b')
    return parser.parse_args()


if __name__ == '__main__':
    main()
