'''
Reference grayscale from a set of reference fonts, and comparison of a font against it.

1. normalize: puts one font's coverage on a scale shared by all fonts, using the font's own distribution over a
   fixed basis set of characters (by default the 3,500 common characters of the 通用规范汉字表).
2. build_reference: each character's reference position is its median normalized value across the reference
   fonts. Sorting characters by position gives the canonical grayscale ordering (Reference.ordering).
3. fit_tone_curve: the target font's coverage as a smooth function of reference position, fitted on the glyphs
   it has. It shows how this font maps the canonical ordering to actual darkness, and predicts where glyphs
   that are not drawn yet should land.
4. compare: each glyph's residual from its font's tone curve: positive means darker than expected.

evaluate_fit scores a tone curve on glyphs held out from fitting, so models can be compared by how well they
predict rather than how closely they fit.
'''

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Iterable, Literal, Sequence

import numpy as np

from fontbench.charsets import tongyong_guifan
from fontbench.measure import FontMeasurement


Normalization = Literal['ratio', 'robust_z', 'normal_score']
Model = Literal['linear', 'spline']
Value = Literal['coverage', 'lightness']

# Converts a median absolute deviation or interquartile range into a standard deviation, for normal data
_MAD_TO_SD = 1.4826
_IQR_TO_SD = 1 / 1.3490
# Quantiles of the fitted positions where spline knots go, by number of knots (Harrell, Regression Modeling
# Strategies, table 2.3). Outer knots sit inside the data, so the curve is already straight in the far tails.
_KNOT_QUANTILES = {
    3: (0.10, 0.50, 0.90),
    4: (0.05, 0.35, 0.65, 0.95),
    5: (0.05, 0.275, 0.50, 0.725, 0.95),
    6: (0.05, 0.23, 0.41, 0.59, 0.77, 0.95),
    7: (0.025, 0.1833, 0.3417, 0.50, 0.6583, 0.8167, 0.975),
}


# Normalization

def normalize(
    m: FontMeasurement,
    method: Normalization = 'normal_score',
    basis: Iterable[str] | None = None,
    min_basis_coverage: float = 0.9,
) -> dict[str, float]:
    '''
    Puts every measured character's coverage on a scale that does not depend on the font's weight or overall
    darkness. The scale is set by the font's coverage over `basis` alone, so fonts with very different
    character sets are normalized alike.

    Methods:
        ratio: coverage / basis median. Corrects overall darkness only.
        robust_z: (coverage - basis median) / basis standard deviation, estimated from the interquartile range.
            Corrects darkness and spread; the probit model's two parameters, estimated robustly.
        normal_score: the character's percentile among the basis glyphs, converted to standard normal units
            (50% -> 0, 84% -> +1). Corrects the whole shape of the distribution. Values outside the basis
            range are extrapolated linearly from the outermost basis glyphs, so they keep their order.

    Arguments:
        basis: Characters that set the scale. Defaults to level 1 of the 通用规范汉字表.
        min_basis_coverage: Raise ValueError if the font has fewer than this share of the basis characters.
    '''
    basis = tongyong_guifan(1) if basis is None else frozenset(basis)
    chars = list(m.by_char)
    values = np.array([m.by_char[c].coverage for c in chars])
    basis_values = np.array([m.by_char[c].coverage for c in basis if c in m.by_char])
    if len(basis_values) < max(10, min_basis_coverage * len(basis)):
        raise ValueError(
            f'{m.font_id} has {len(basis_values)} of {len(basis)} basis characters; '
            f'at least {min_basis_coverage:.0%} (and 10) are needed.'
        )

    median = float(np.median(basis_values))
    if method == 'ratio':
        normalized = values / median
    elif method == 'robust_z':
        q1, q3 = np.percentile(basis_values, [25, 75])
        normalized = (values - median) / ((q3 - q1) * _IQR_TO_SD)
    elif method == 'normal_score':
        normalized = _normal_scores(values, basis_values)
    else:
        raise ValueError(f"Unknown normalization {method!r}; use 'ratio', 'robust_z' or 'normal_score'.")
    return dict(zip(chars, normalized.tolist()))


def _normal_scores(values: np.ndarray, basis_values: np.ndarray) -> np.ndarray:
    n = len(basis_values)
    inv_cdf = NormalDist().inv_cdf
    sorted_values = np.sort(basis_values)
    scores = np.array([inv_cdf((i + 0.5) / n) for i in range(n)])
    # Tied values share the mean of their scores, so interpolation sees a strictly increasing table
    unique, inverse = np.unique(sorted_values, return_inverse=True)
    unique_scores = np.bincount(inverse, weights=scores) / np.bincount(inverse)
    if len(unique) < 2:
        raise ValueError('All basis glyphs have the same coverage.')

    result = np.interp(values, unique, unique_scores)
    # Extrapolate linearly, with the slope over the outermost 2.5% of basis glyphs at each end
    k = min(len(unique) - 1, max(1, len(unique) // 40))
    low_slope = (unique_scores[k] - unique_scores[0]) / (unique[k] - unique[0])
    high_slope = (unique_scores[-1] - unique_scores[-1 - k]) / (unique[-1] - unique[-1 - k])
    below, above = values < unique[0], values > unique[-1]
    result[below] = unique_scores[0] + (values[below] - unique[0]) * low_slope
    result[above] = unique_scores[-1] + (values[above] - unique[-1]) * high_slope
    return result


# Shape of a font's distribution

@dataclass(frozen=True)
class ShapeSummary:
    '''The shape of one font's coverage distribution over a basis set, for comparing fonts as a whole.'''
    n: int
    median: float
    # Interquartile range / median: how far apart simple and complex glyphs are, relative to overall darkness
    relative_spread: float
    # Moment skewness; negative means a long tail of light (simple) glyphs
    skew: float


def shape_summary(m: FontMeasurement, basis: Iterable[str] | None = None) -> ShapeSummary:
    '''Summarizes a font's coverage distribution over `basis` (default: level 1 of the 通用规范汉字表).'''
    basis = tongyong_guifan(1) if basis is None else frozenset(basis)
    values = np.array([m.by_char[c].coverage for c in basis if c in m.by_char])
    if len(values) < 3:
        raise ValueError(f'{m.font_id} has fewer than 3 basis characters.')
    median = float(np.median(values))
    q1, q3 = np.percentile(values, [25, 75])
    centered = values - values.mean()
    sd = centered.std()
    skew = float((centered ** 3).mean() / sd ** 3) if sd > 0 else 0.0
    return ShapeSummary(len(values), median, float((q3 - q1) / median), skew)


# Reference

@dataclass(frozen=True)
class ReferenceSettings:
    normalization: Normalization = 'normal_score'
    # Characters whose distribution sets each font's scale (see normalize)
    basis: frozenset[str] = field(default_factory=lambda: tongyong_guifan(1))
    # Each reference font must have at least this share of the basis
    min_basis_coverage: float = 0.9
    # Characters covered by fewer reference fonts get no reference position
    min_fonts: int = 1


@dataclass(frozen=True)
class CharReference:
    char: str
    # Median normalized value across the reference fonts
    position: float
    # Disagreement between reference fonts: scaled median absolute deviation (0 with a single font)
    spread: float
    n_fonts: int
    # Each reference font's normalized value, by font_id
    by_font: dict[str, float]


@dataclass(frozen=True)
class Reference:
    settings: ReferenceSettings
    font_ids: tuple[str, ...]
    by_char: dict[str, CharReference]
    # Each reference font's distribution shape over the basis, by font_id
    shapes: dict[str, ShapeSummary]

    def ordering(self) -> list[str]:
        '''Characters from lightest to darkest reference position: the canonical grayscale ordering.'''
        return sorted(self.by_char, key=lambda c: self.by_char[c].position)

    def positions(self, exclude: str | None = None) -> dict[str, float]:
        '''Reference position of every character, optionally recomputed without one reference font.'''
        return {char: stats[0] for char, stats in self.stats(exclude).items()}

    def stats(self, exclude: str | None = None) -> dict[str, tuple[float, float, int]]:
        '''
        {character: (position, spread, n_fonts)}. With `exclude`, that font's values are left out (characters
        then covered by fewer than min_fonts fonts are dropped); otherwise the stored values are returned.
        '''
        if exclude is None or exclude not in self.font_ids:
            return {c: (r.position, r.spread, r.n_fonts) for c, r in self.by_char.items()}
        result = {}
        for char, ref in self.by_char.items():
            values = [v for font_id, v in ref.by_font.items() if font_id != exclude]
            if len(values) >= self.settings.min_fonts and values:
                result[char] = _location_and_spread(values) + (len(values),)
        return result


def build_reference(measurements: Iterable[FontMeasurement], settings: ReferenceSettings | None = None) -> Reference:
    '''
    Builds a reference from measurements of reference fonts. Each measurement's font_id must be unique.
    Pick comparable fonts and masters (e.g. similar weights, same region's character forms) before calling.
    '''
    settings = settings or ReferenceSettings()
    measurements = list(measurements)
    font_ids = tuple(m.font_id for m in measurements)
    if not measurements:
        raise ValueError('No reference fonts given.')
    if len(set(font_ids)) != len(font_ids):
        raise ValueError(f'Reference font_ids must be unique, got {font_ids}.')

    values_by_char: dict[str, dict[str, float]] = {}
    shapes = {}
    for m in measurements:
        normalized = normalize(m, settings.normalization, settings.basis, settings.min_basis_coverage)
        for char, value in normalized.items():
            values_by_char.setdefault(char, {})[m.font_id] = value
        shapes[m.font_id] = shape_summary(m, settings.basis)

    by_char = {}
    for char, by_font in values_by_char.items():
        if len(by_font) < settings.min_fonts:
            continue
        position, spread = _location_and_spread(list(by_font.values()))
        by_char[char] = CharReference(char, position, spread, len(by_font), by_font)
    return Reference(settings, font_ids, by_char, shapes)


def _location_and_spread(values: Sequence[float]) -> tuple[float, float]:
    array = np.asarray(values)
    median = float(np.median(array))
    spread = float(_MAD_TO_SD * np.median(np.abs(array - median))) if len(array) > 1 else 0.0
    return median, spread


# Tone curves

@dataclass(frozen=True)
class ToneCurve:
    '''
    A font's coverage (or lightness) as a function of reference position.

    linear: value = a + b * position. With normal_score positions this is the probit model.
    spline: a natural cubic spline in position. It bends between its knots and is straight beyond the outer
        knots, so predictions for positions past the fitted glyphs continue along a line.
    '''
    model: Model
    value: Value
    knots: tuple[float, ...]
    coefficients: tuple[float, ...]
    # Number of glyphs the curve was fitted on, and the range of their positions
    n_glyphs: int
    position_range: tuple[float, float]

    def predict(self, positions):
        '''The expected value at one position (returns a float) or at an array of positions.'''
        x = np.asarray(positions, dtype=float)
        result = _design_matrix(np.atleast_1d(x), self.model, self.knots) @ np.asarray(self.coefficients)
        return float(result[0]) if x.ndim == 0 else result

    def slope(self, positions):
        '''The curve's derivative, i.e. value change per unit of position.'''
        h = 1e-4
        x = np.asarray(positions, dtype=float)
        return (self.predict(x + h) - self.predict(x - h)) / (2 * h)

    def is_monotone(self) -> bool:
        '''Whether the curve only gets darker with position over its fitted range.'''
        grid = np.linspace(*self.position_range, 200)
        steps = np.diff(self.predict(grid))
        return bool(np.all(steps >= 0) if self.value == 'coverage' else np.all(steps <= 0))


def fit_tone_curve(
    target: FontMeasurement,
    reference: Reference,
    model: Model = 'spline',
    value: Value = 'coverage',
    knots: int | Sequence[float] = 5,
    smoothing: float = 0.0,
    robust: bool = True,
    chars: Iterable[str] | None = None,
    exclude_self: bool = True,
) -> ToneCurve:
    '''
    Fits the target font's tone curve on its glyphs that have a reference position.

    Arguments:
        model: 'linear' or 'spline' (see ToneCurve).
        value: Fit coverage or L* lightness.
        knots: For splines, the number of knots (placed at quantiles of the fitted positions) or their positions.
        smoothing: For splines, shrinks the curve toward a straight line; 0 means no shrinkage, and large
            values give the linear model.
        robust: Down-weight glyphs far from the curve (Huber weights), so the badly drawn glyphs this is meant
            to find do not bend it.
        chars: Fit only these characters, e.g. to hold others out for evaluate_fit.
        exclude_self: If the target is one of the reference fonts, compute positions without it.
    '''
    positions = reference.positions(target.font_id if exclude_self else None)
    selected = target.by_char.keys() & positions.keys()
    if chars is not None:
        selected &= set(chars)
    selected = sorted(selected)
    x = np.array([positions[c] for c in selected])
    y = np.array([_value(target, c, value) for c in selected])

    if model == 'linear':
        knot_positions: tuple[float, ...] = ()
    elif model == 'spline':
        if isinstance(knots, int):
            quantiles = _KNOT_QUANTILES.get(knots, tuple(np.linspace(0.05, 0.95, knots)))
            knot_positions = tuple(np.quantile(x, quantiles).tolist()) if len(x) else ()
        else:
            knot_positions = tuple(sorted(float(k) for k in knots))
        if len(knot_positions) < 3 or len(set(knot_positions)) != len(knot_positions):
            raise ValueError(f'A spline needs at least 3 distinct knots, got {knot_positions}.')
    else:
        raise ValueError(f"Unknown model {model!r}; use 'linear' or 'spline'.")

    design = _design_matrix(x, model, knot_positions)
    if len(x) < 2 * design.shape[1]:
        raise ValueError(f'{len(x)} glyphs with reference positions are too few to fit a {model} curve.')
    penalty = np.zeros(design.shape[1])
    penalty[2:] = smoothing * len(x)
    coefficients = _fit(design, y, penalty, robust)
    return ToneCurve(model, value, knot_positions, tuple(coefficients.tolist()), len(x), (float(x.min()), float(x.max())))


def _value(m: FontMeasurement, char: str, value: Value) -> float:
    return m.by_char[char].coverage if value == 'coverage' else m.by_char[char].lightness


def _design_matrix(x: np.ndarray, model: Model, knots: Sequence[float]) -> np.ndarray:
    columns = [np.ones_like(x), x]
    if model == 'spline':
        # Natural cubic spline basis (Hastie, Tibshirani & Friedman, Elements of Statistical Learning, eq. 5.4–5.5)
        k = np.asarray(knots)

        def d(j):
            return (np.maximum(x - k[j], 0) ** 3 - np.maximum(x - k[-1], 0) ** 3) / (k[-1] - k[j])

        last = d(len(k) - 2)
        columns += [d(j) - last for j in range(len(k) - 2)]
    return np.column_stack(columns)


def _fit(design: np.ndarray, y: np.ndarray, penalty: np.ndarray, robust: bool) -> np.ndarray:
    '''Penalized least squares, iteratively reweighted with Huber weights if `robust`.'''
    weights = np.ones(len(y))
    coefficients = np.zeros(design.shape[1])
    for _ in range(50 if robust else 1):
        weighted = design * weights[:, None]
        new = np.linalg.solve(design.T @ weighted + np.diag(penalty), weighted.T @ y)
        converged = np.allclose(new, coefficients, rtol=1e-9, atol=1e-12)
        coefficients = new
        if converged:
            break
        residuals = y - design @ coefficients
        scale = _MAD_TO_SD * np.median(np.abs(residuals - np.median(residuals)))
        if scale == 0:
            break
        u = np.abs(residuals) / (1.345 * scale)
        weights = np.where(u <= 1, 1.0, 1 / np.maximum(u, 1e-12))
    return coefficients


# Comparison

@dataclass(frozen=True)
class Deviation:
    char: str
    glyph_name: str
    strokes: int | None
    # Reference position, the reference fonts' disagreement there, and how many fonts it rests on
    position: float
    spread: float
    n_fonts: int
    # The glyph's value, the tone curve's value at its position, and the difference (actual - expected).
    # With value='coverage', positive means darker than expected; with 'lightness', lighter.
    actual: float
    expected: float
    residual: float
    # Residual / the font's typical residual: how unusual this glyph is among the font's own glyphs
    score: float
    # Residual / the reference fonts' disagreement at this position (converted to value units with the curve's
    # slope). None when the reference fonts cannot disagree (a single font).
    spread_score: float | None


@dataclass(frozen=True)
class Comparison:
    font_id: str
    curve: ToneCurve
    # Robust standard deviation of all residuals; Deviation.score is in these units
    residual_scale: float
    deviations: dict[str, Deviation]
    # Expected values for characters the reference has and the font does not: where undrawn glyphs should land
    predictions: dict[str, float]
    shape: ShapeSummary | None


def compare(
    target: FontMeasurement,
    reference: Reference,
    curve: ToneCurve | None = None,
    exclude_self: bool = True,
    **fit_options,
) -> Comparison:
    '''
    Compares every glyph of the target font with its tone curve.

    Arguments:
        curve: A tone curve fitted earlier; by default one is fitted with fit_tone_curve(**fit_options).
        exclude_self: If the target is one of the reference fonts, compute positions without it.
    '''
    if curve is None:
        curve = fit_tone_curve(target, reference, exclude_self=exclude_self, **fit_options)
    stats = reference.stats(target.font_id if exclude_self else None)
    chars = sorted(target.by_char.keys() & stats.keys())
    positions = np.array([stats[c][0] for c in chars])
    actual = np.array([_value(target, c, curve.value) for c in chars])
    expected = curve.predict(positions)
    residuals = actual - expected
    scale = float(_MAD_TO_SD * np.median(np.abs(residuals - np.median(residuals)))) if len(chars) else 0.0
    slopes = np.abs(curve.slope(positions))

    deviations = {}
    for i, char in enumerate(chars):
        position, spread, n_fonts = stats[char]
        tolerance = slopes[i] * spread
        glyph = target.by_char[char]
        deviations[char] = Deviation(
            char=char,
            glyph_name=glyph.glyph_name,
            strokes=glyph.strokes,
            position=position,
            spread=spread,
            n_fonts=n_fonts,
            actual=float(actual[i]),
            expected=float(expected[i]),
            residual=float(residuals[i]),
            score=float(residuals[i] / scale) if scale > 0 else 0.0,
            spread_score=float(residuals[i] / tolerance) if tolerance > 0 else None,
        )

    missing = sorted(stats.keys() - target.by_char.keys())
    predicted = curve.predict(np.array([stats[c][0] for c in missing])) if missing else []
    try:
        shape = shape_summary(target, reference.settings.basis)
    except ValueError:
        shape = None
    return Comparison(target.font_id, curve, scale, deviations, dict(zip(missing, map(float, predicted))), shape)


# Evaluation

@dataclass(frozen=True)
class FitEvaluation:
    '''Errors of a tone curve's predictions for glyphs it was not fitted on (predicted - actual).'''
    curve: ToneCurve
    n_train: int
    n_test: int
    bias: float
    mean_abs_error: float
    median_abs_error: float
    rmse: float
    max_abs_error: float


def evaluate_fit(
    target: FontMeasurement,
    reference: Reference,
    train: Iterable[str],
    test: Iterable[str],
    exclude_self: bool = True,
    **fit_options,
) -> FitEvaluation:
    '''
    Fits a tone curve on the `train` characters and scores its predictions for the `test` characters. Test
    characters the font or reference does not have are ignored. E.g. train on level 1 of the 通用规范汉字表
    and test on level 2, to see how well a curve from common glyphs predicts rarer ones.
    '''
    train = set(train)
    curve = fit_tone_curve(target, reference, chars=train, exclude_self=exclude_self, **fit_options)
    positions = reference.positions(target.font_id if exclude_self else None)
    test_chars = sorted((set(test) & target.by_char.keys() & positions.keys()) - train)
    if not test_chars:
        raise ValueError('None of the test characters are in both the font and the reference.')
    predicted = curve.predict(np.array([positions[c] for c in test_chars]))
    actual = np.array([_value(target, c, curve.value) for c in test_chars])
    errors = predicted - actual
    return FitEvaluation(
        curve=curve,
        n_train=curve.n_glyphs,
        n_test=len(test_chars),
        bias=float(errors.mean()),
        mean_abs_error=float(np.abs(errors).mean()),
        median_abs_error=float(np.median(np.abs(errors))),
        rmse=float(np.sqrt((errors ** 2).mean())),
        max_abs_error=float(np.abs(errors).max()),
    )
