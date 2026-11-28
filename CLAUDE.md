# CLAUDE.md

## Purpose

FontBench measures Chinese typefaces so a type designer can judge each glyph against a **reference grayscale**:
is this glyph too dark or too light compared with the rest of the font? The reference comes from a set of
well-made reference fonts in the same style. Each character's darkness is normalized within each font, and the
median across fonts gives a canonical grayscale ordering of characters.

The main use case: design about 3,000 glyphs, fit how this font maps the canonical ordering to actual darkness,
then **predict where the rest of the glyphs (e.g. the rest of the 9169 set) should land**, and flag drawn glyphs
that deviate.

Predicting darkness from complexity within one font (e.g. from stroke count) was considered and rejected; stroke
counts are kept as a descriptive field and for analysis only.

## Repository layout

```
fontbench/         The library. See below.
experiments/
  grayscale/
    measure.py               Measuring CLI (see Running)
    Grayscale Analysis.ipynb Plots of earlier grayscale data (see Earlier experiments)
    data/                    Earlier grayscale measurements, in the old JSONL format
  sidebearings/
    树枝笔画标签综合.xlsx, char-labels.json   Hand-labelled outermost strokes (see Earlier experiments)
  validation/                Phase 4: validating reference grayscale on the 黑体 corpus (see Validation)
    corpus.py                Font list grouped by design family; measurement cache in data/ (gitignored)
    validate.py              Normalization, tone-curve and reference-choice comparisons → output/validation/
    deviations.py            HTML page of one font's most-flagged glyphs, for checking by eye
    weight_bias.py           Reference darkness limits vs stroke-related bias, light/mid/heavy targets
  strokes/
    export_strokes.py        Stroke count per character of a charset (9169, tgh levels or a text file) → CSV/XLSX
tools/
  build_stroke_tables.py   Builds fontbench/data/stroke_counts.pickle from Unihan
glyphs/            Glyphs source files (gitignored)
```

Reference fonts live outside the repo, in the parent folder: `../各种黑体大全/` (黑体 references, mostly in
`字体/`) and `../Fonts/`.

## Earlier experiments

The library was rewritten from scratch. The scripts below were written against the previous library and have
been deleted; they are in git history and in `../fontbench (backup)`. What they did:

- **Grayscale measurement** (`grayscale/main.py`): measured every glyph in every master of a `.glyphs` file
  (offering to cache the parsed `GSFont` as a pickle) or a TTF/OTF. It wrote JSONL rows of
  `{id, string, unicode, grayscale: {master: value}}`, which is the format of `grayscale/data/*.jsonl`. Grayscale
  was first measured by rasterizing with pyvips, then from outlines. `measure.py` replaces it.
- **Consistency checks** (`grayscale/tests.py`, `grayscale/compare-ttf-glyphs.py`): checked the outline
  ("integration") grayscale against the raster one (to within 1e-2), and a TTF against its Glyphs source (to
  within 1%). Three OPPO Sans 4.0 glyphs still disagreed and were set aside: `aringacute`, `uni2043` and
  `uniFE19`, the last fixed by measuring height from the font's vertical metrics instead of `vertWidth`.
  `aringacute.svg`, `uni2043.svg` and `uniFE19.svg` in the repo root are from that investigation.
- **Grayscale analysis** (`Grayscale Analysis.ipynb`, kept): filters to Hanzi, plots glyphs sorted by grayscale,
  their histogram, and comparisons between fonts. The sorted-grayscale curve has much the same shape in every
  font tested, which is what the tone-curve models describe.
- **Sidebearings and outermost "branch" strokes** (`sidebearings/`): on the 3type 9169 Glyphs file (ExtraLight,
  Regular and Heavy masters), it read each glyph's four sidebearings from its bounds, with the top and bottom
  measured from descender and ascender. It found the outermost strokes in each direction (on-curve nodes tied
  at the extreme coordinate, with adjacent ones merged into one stroke) and their extent along that edge. The
  results were joined with hand labels of which stroke type sits on each side (树枝笔画, from the xlsx, turned
  into `char-labels.json`) and exported to a multi-sheet Excel workbook. It also compared how stable the
  sidebearing rankings are across weights with Kendall's τ, over all characters and over random batches.

## The library

A narrow, purpose-built analysis library on top of fontTools and glyphsLib, not a general font library. Every
function returns plain Python objects (dataclasses, dicts, floats). File formats, caching, plotting and UI
belong in the scripts and apps that use it. Use fontTools and glyphsLib directly unless a wrapper encodes a
decision or fills a real gap.

### Modules, in dependency order

- **`sources/`**: one interface over font formats.
  - `Font` and `Glyph` are Protocols. Implementations: `GlyphsFont` (a `.glyphs` file or a parsed `GSFont`;
    master layers only) and `CompiledFont` (TTF/OTF/TTC/OTC; for variable fonts, the masters are the `fvar` named
    instances). `open_font(path_or_gsfont)` picks the right one.
  - A glyph's `frame` is a `Box` from 0 to the advance width horizontally, and from descender to ascender
    vertically.
  - Gotcha: in a variable font without HVAR, fontTools only interpolates the advance width once the glyph has
    been drawn. `CompiledGlyph.advance` relies on this.
- **`metrics.py`**: per-glyph numbers.
  - `outline_statistics` is a fontTools `StatisticsPen`, with overlaps removed by skia-pathops by default.
  - `coverage` = |ink area| / frame area.
  - `lightness` converts coverage to CIE L*.
  - Everything is computed from outlines, with no rasterizing (vips was removed on purpose).
- **`strokes.py`**: total stroke counts.
  - `stroke_count(char, convention)` has two conventions:
    - `'mainland'` (zh-Hans) is Unihan 15.0 `kTotalStrokes`, the last release before it switched to IRG
      counting, with 41 counts corrected from the 通用规范汉字表 order.
    - `'irg'` is the latest Unihan.
  - The data is read from `fontbench/data/stroke_counts.pickle`, which also holds the `kTGH` positions.
- **`charsets.py`**: standard character sets.
  - `tongyong_guifan(*levels)` returns 通用规范汉字表 levels 1–3 (3,500, 3,000 and 1,605 characters). Level 1 is
    the default basis for normalization.
  - `tongyong_guifan_level(char)` gives a character's level.
  - `chars_9169()` is the 9169 set Chinese fonts are commonly designed for. It is stored in `sets/9169.txt`,
    whose header documents its source and contents.
- **`measure.py`**: measuring a whole font.
  - `GlyphMeasurement` holds char, glyph_name, advance, coverage, lightness and strokes. It has no font field on
    purpose: the container carries the font information.
  - `FontMeasurement` holds font_id, family, master and stroke_convention, plus `by_char: {char: GlyphMeasurement}`
    and `skipped: {char: SkipReason}`.
  - `measure_glyph` never skips; an empty glyph gets coverage 0.
  - `measure_font(font, master, chars=..., progress=tqdm)` is the only place that decides what to skip.
- **`reference.py`**: reference grayscale and comparison against it.
  - `normalize(m, method, basis)` puts one font on a shared scale using its own distribution over a fixed basis
    set:
    - `ratio` divides by the median.
    - `robust_z` is (x − median) / (IQR / 1.349).
    - `normal_score` (the default) passes each value's percentile in the basis through Φ⁻¹, extending linearly
      beyond the basis range.
  - `build_reference(measurements, ReferenceSettings)` returns a `Reference`:
    - Per character: position = the median of the normalized values, spread = 1.4826 × MAD, plus per-font values.
    - `.ordering()` gives the canonical grayscale order.
    - `exclude=` gives leave-one-out positions.
  - `fit_tone_curve(target, reference, model=...)` fits the target's coverage (or lightness) as a function of
    reference position, returning a `ToneCurve`:
    - `'linear'` is the probit model.
    - `'spline'` is a natural cubic spline, linear beyond its outer knots, with knots at Harrell quantiles.
      `smoothing` is a ridge penalty that shrinks it toward linear.
    - Both fits are robust (IRLS with Huber weights).
  - `compare(target, reference)` returns a `Comparison`: a `Deviation` per glyph (positive residual = darker
    than expected; `score` = residual / robust residual scale) and `predictions` for characters the target lacks.
  - `evaluate_fit(target, reference, train, test)` scores a curve on held-out glyphs. Compare models by held-out
    prediction, not in-sample fit.

### Conventions

- numpy only for numerics (no scipy); `statistics.NormalDist` for Φ⁻¹.
- Results are keyed by character, not glyph name.
- Docstrings explain decisions and units. Comments explain *why*, not *what*.
- Model choices (normalization, linear vs. spline, knots, smoothing, reference set) are the user's to examine
  and compare. The library provides the tools and sensible defaults, not a verdict.

## Data tables

`fontbench/data/` is **gitignored on purpose**, so a fresh clone has to build the stroke table:

```bash
python tools/build_stroke_tables.py
```

If the pickle is missing, `fontbench.strokes` raises an error naming this command. `fontbench/sets/` is
committed, because its source font files are not in the repo.

## Running

uv-managed, Python 3.13. The project is installed into `.venv` in editable mode, which records the repo's
absolute path; if the repo folder moves, reinstall with `uv pip install -e . --no-deps`. Use the project venv:

```bash
.venv/bin/python experiments/grayscale/measure.py ../各种黑体大全/字体/*.otf --master Regular -o regular.pickle
```

`measure.py` writes `.jsonl` (one row per character and master) or `.pickle` (a list of `FontMeasurement`), and
accepts `.glyphs` files, pickled `GSFont`s (to skip slow parsing) and compiled fonts.

Validation (phase 4):

```bash
.venv/bin/python experiments/validation/corpus.py      # measure the corpus once (~3 min), cached
.venv/bin/python experiments/validation/validate.py    # all sections (~4 min); --sections 1 2 3 4
.venv/bin/python experiments/validation/deviations.py "OPPOSans Regular"
.venv/bin/python experiments/validation/deviations.py --font glyphs/书宋.glyphs --master Regular
```

## Validation

The corpus is 87 SC masters in 37 design families from `../各种黑体大全`, from about 0.10 median coverage (苹方
极细) to 0.59 (兰亭黑 Heavy). Two TC fonts are measured but kept out of SC references. A target is only compared
with references from other design families: by default, the master of each family closest to it in darkness,
if it is within 1.5× of the target's darkness (see Weight bias).
Errors are mean absolute errors on held-out glyphs, as % of the target's median coverage, with the median taken
over targets.

Findings (2026-11-25):
- **Normalization matters more than the model, and mostly in the tails.** Predicting levels 2–3 from level 1
  gives about 2.25% for every normalization and spline. For the darkest and lightest 10% of glyphs, normal_score
  positions do worst: linear 5.8% and 7.7%, spline k5 2.7% and 3.1%. robust_z with spline k5 gives 2.8% and
  2.0%. normal_score squeezes each font's tails into a fixed shape and saturates at the basis extremes. For
  example, 一 gets the same position in every font, and single-stroke glyphs come out systematically "too light".
  ratio and robust_z predict almost identically.
- With robust_z or ratio positions, even the linear model is close (2.3% on levels 2–3, about 3% on the tails).
  The spline mainly helps in the tails. k5 and k7 are equal, k3 is slightly worse, and smoothing=0.1 hurts the
  tails.
- Light fonts are harder to predict (about 2.6% vs 2.1%). The worst-predicted families are stylistically unusual
  (iLiHei 5%, the rounded M 圆 3.4%).
- **References:**
  - For mid-weight targets, the closest-weight master per family is best. Restricting references to within 1.25×
    darkness doesn't help, and using every master of every family is slightly worse. Light targets are
    different (see the weight-bias finding below).
  - Error falls from 3.3% with 1 reference family to 2.5% with 8, and 2.4% with all 36.
  - Positions from two disjoint halves of 18 families correlate at 0.997 (noise 0.05 vs a single font's typical
    disagreement of 0.18). So the remaining ~2% error is the target's own design, not reference noise.
- **Flagged glyphs cluster by component.** For OPPO Sans R, the glyphs flagged darker are 髟-top characters
  (鬣鬒鬈鬓) and 罍/藟; those flagged lighter are left-口 characters (唰呵嘟喘). These look like consistent design
  choices rather than random errors.
- **Across all 87 SC masters** (deviations.py on each, robust_z, spline k5, before the 1.5× limit below): most
  fonts flag 0.3–1.2% of glyphs
  beyond ±3σ. No character is flagged in more than 11 of 37 families, so flags are font-specific, not reference
  errors. But residuals depend on weight: the correlation of a font's darkness with its score-vs-stroke-count
  correlation is −0.71. Very light masters (IBM Plex Thin, 苹方极细, 青花黑 W1: 3–4% flagged) see dense glyphs
  flagged darker, and heavy masters see them flagged lighter. 方正兰亭黑 flags
  dense glyphs lighter at every weight (a family style). Clusters, as with OPPO: 門 darker in 苹方 and 思源;
  參/翏 lighter in 思源; 鱼 lighter in 冬青; 钅/鸟/贝 lighter in iLiHei (258 lighter flags); 髟 and 雨 lighter in
  兰亭黑. MiSans, HarmonyOS Sans, 阿里巴巴普惠体 and 汉仪旗黑 share most of their flags (罍圙廙藟蒐毐雎 darker,
  雩彳鄂鹗 lighter).
- **Weight bias** (`weight_bias.py`, all 87 masters, binned by median coverage: light < 0.20, heavy ≥ 0.40):
  - Light targets get references that are too dark. With the default matched references (36 families), their
    densest 10% of glyphs are predicted 2.7% too light (median; 6% for IBM Plex Thin and 苹方极细). Limiting
    references to within 1.5× darkness (about 13 families) cuts this to 0.9%, and 1.25× (about 8) to 0.5%.
    Errors fall too: 4.2% → 3.3% on dense glyphs, 2.8% → 2.4% on L1 → L2–3. The flag rate falls from 1.9% to
    1.2%, and the score–stroke correlation from 0.18 to 0.05.
  - Mid-weight targets: no change from any limit.
  - Heavy targets: the dense-glyph bias is mostly the target family's own style. 德赛黑 and 兰亭黑 stay about
    +1% whatever the references, and OPPO Sans goes the other way. 1.5× still gives the lowest errors (L1 → L2–3
    1.97% → 1.82%).
  - Within 1.5× is never worse than no limit in any bin. "All masters within 1.25×" gives no extra benefit.
  - **Decision (2026-11-27): `reference_fonts` now limits references to 1.5× darkness by default.** If that
    leaves fewer than 3, it keeps the 3 closest instead; the lightest corpus masters have exactly 3. deviations.py
    uses the default (`--max-darkness-ratio 0` for no limit). validate.py and weight_bias.py pass
    `max_darkness_ratio=None` for their baselines, so the numbers recorded above still reproduce. Regenerating
    all 87 pages cut flags from 7,930 to 7,060: IBM Plex Thin 426 → 132, 苹方极细 388 → 130. A few fonts gained
    flags, most of all iLiHei (261 → 308) and the 细等线 fonts (about +34).

## Status

- **Phase 1** (sources, metrics, strokes), **phase 2** (measure), **phase 3** (reference, tone curves,
  comparison) and **phase 4** (validation, see above) are done.
- Open decision: the library's default normalization is still normal_score, though validation favors robust_z
  for prediction. normal_score still has the lowest cross-font disagreement overall and in the light tail, but
  the highest in the dark tail.
- On hold: a "clumping" metric (how ink is distributed within the frame), pending more planning.

## Working rules

- Don't commit unless asked.
- Don't add vips or other rasterizing dependencies.
