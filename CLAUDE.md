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

## Status

- **Phase 1** (sources, metrics, strokes), **phase 2** (measure) and **phase 3** (reference, tone curves,
  comparison) are done.
- Results so far (OPPO Sans R against five 黑体 references):
  - `normal_score` gives the lowest cross-font spread, but only slightly.
  - Fitted on level 1, the spline predicts levels 2–3 with a mean error of about 1.4% of the median coverage.
  - The linear model misfits both tails.
- **Phase 4** (next) is a validation script, not library code:
  - Measure many fonts.
  - Compare normalizations by cross-font spread.
  - Compare linear and spline curves with `evaluate_fit` on realistic splits (level 1 → levels 2–3, a subset →
    the rest of 9169, light → darkest tail).
  - Check the top flagged glyphs by eye.
  - Test how sensitive results are to the reference fonts chosen.
- On hold: a "clumping" metric (how ink is distributed within the frame), pending more planning.

## Working rules

- Don't commit unless asked.
- Don't add vips or other rasterizing dependencies.
