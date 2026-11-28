'''
Writes an HTML page of the glyphs in one font that deviate most from its tone curve, for checking by eye whether
the flagged glyphs really look too dark or too light. Each flagged glyph is shown next to glyphs of the same font
that the reference places at about the same position and that fit the curve well.

The target is a corpus font (by font_id), or any font file. References come from the corpus (see corpus.py):
from each other design family, the master closest in darkness.

    python experiments/validation/deviations.py "OPPOSans Regular"
    python experiments/validation/deviations.py --font ../glyphs/书宋.glyphs --master Regular

Writes output/validation/deviations/<font_id>.html, and a .csv of every glyph's deviation and the predicted
coverage of characters the font does not have.
'''

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from fontTools.pens.svgPathPen import SVGPathPen
from tqdm import tqdm

import fontbench as fb
from corpus import CHARS, FONT_ROOT, REPO, CorpusFont, Source, load_corpus, reference_fonts
from validate import MODELS, NORMALIZATIONS


OUTPUT = REPO / 'output' / 'validation' / 'deviations'
NEIGHBORS = 5


def main():
    args = parse_args()
    corpus = load_corpus()
    target, font = load_target(args, corpus)
    refs = reference_fonts(target, corpus, max_darkness_ratio=args.max_darkness_ratio or None)
    reference = fb.build_reference([f.measurement for f in refs],
                                   fb.ReferenceSettings(normalization=args.normalization))
    comparison = fb.compare(target.measurement, reference, **MODELS[args.model])
    deviations = sorted(comparison.deviations.values(), key=lambda d: d.score)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    stem = target.font_id.replace('/', '-')
    rows = [dict(char=d.char, glyph_name=d.glyph_name, strokes=d.strokes, position=d.position, spread=d.spread,
                 actual=d.actual, expected=d.expected, residual=d.residual, score=d.score) for d in deviations]
    rows += [dict(char=c, position=reference.by_char[c].position, expected=v) for c, v in comparison.predictions.items()]
    pd.DataFrame(rows).to_csv(OUTPUT / f'{stem}.csv', index=False)

    page = render_page(target, font, refs, comparison, deviations, args)
    path = OUTPUT / f'{stem}.html'
    path.write_text(page, encoding='utf-8')
    print(f'Wrote {path}')


def load_target(args, corpus: list[CorpusFont]) -> tuple[CorpusFont, fb.Font]:
    if args.font is None:
        matches = [f for f in corpus if f.font_id == args.font_id]
        if not matches:
            sys.exit(f'No corpus font "{args.font_id}". Font ids:\n  ' + '\n  '.join(f.font_id for f in corpus))
        target = matches[0]
        return target, fb.open_font(FONT_ROOT / target.source.path, target.source.font_number)

    font = fb.open_font(args.font, args.font_number)
    master = args.master or font.default_master
    m = fb.measure_font(font, master, chars=CHARS, progress=lambda items: tqdm(items, desc='Measuring', leave=False))
    # A group no corpus font has, so every family can be a reference unless excluded
    target = CorpusFont(Source(str(args.font), group=args.exclude_group or '(target)'), m)
    return target, font


# Page

def render_page(target: CorpusFont, font: fb.Font, refs: list[CorpusFont], comparison: fb.Comparison,
                deviations: list[fb.Deviation], args) -> str:
    master = target.measurement.master
    good = [d for d in deviations if abs(d.score) < 1]
    good_positions = np.array([d.position for d in good])

    def neighbors(d: fb.Deviation) -> list[fb.Deviation]:
        nearest = np.argsort(np.abs(good_positions - d.position))[:NEIGHBORS]
        return sorted((good[i] for i in nearest), key=lambda n: n.position)

    def cards(items: list[fb.Deviation]) -> str:
        out = []
        for d in items:
            glyph = font.glyph_for_char(d.char, master)
            others = ''.join(f'<figure class="small">{glyph_svg(font.glyph_for_char(n.char, master))}'
                             f'<figcaption>{html.escape(n.char)} {n.score:+.1f}</figcaption></figure>'
                             for n in neighbors(d))
            out.append(f'''
<section class="card">
  <figure class="main">{glyph_svg(glyph)}</figure>
  <div class="info">
    <div class="char">{html.escape(d.char)} <span class="name">{html.escape(d.glyph_name)}</span></div>
    <div class="score {'dark' if d.score > 0 else 'light'}">{d.score:+.1f}σ</div>
    <div>coverage {d.actual:.3f}, expected {d.expected:.3f} ({d.residual / d.expected:+.1%})</div>
    <div>position {d.position:+.2f} ± {d.spread:.2f}, {d.strokes or '?'} strokes</div>
  </div>
  <div class="neighbors">{others}</div>
</section>''')
        return ''.join(out)

    darker = [d for d in reversed(deviations) if d.score > 0][:args.top]
    lighter = [d for d in deviations if d.score < 0][:args.top]
    curve = comparison.curve
    reference_list = ', '.join(html.escape(f.font_id) for f in refs)
    flagged = sum(abs(d.score) >= 3 for d in deviations)
    return f'''<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(target.font_id)} deviations</title>
<style>
:root {{ --bg: #fbfaf8; --fg: #1d1d1b; --muted: #77756f; --line: #e3e1dc; --ink: #1d1d1b;
         --dark: #b8432f; --light: #2f6db8; --frame: #d9d6cf; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #1b1b1a; --fg: #ecebe7; --muted: #9a978f; --line: #34332f; --ink: #ecebe7;
           --dark: #e0705b; --light: #6fa0e0; --frame: #45433e; }}
}}
body {{ background: var(--bg); color: var(--fg); font: 14px/1.5 -apple-system, "PingFang SC", sans-serif;
        margin: 0 auto; padding: 24px 16px 64px; max-width: 1100px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }} h2 {{ font-size: 17px; margin: 32px 0 12px; }}
.meta {{ color: var(--muted); }}
.plot {{ width: 100%; height: auto; border: 1px solid var(--line); border-radius: 8px; margin-top: 16px; }}
.card {{ display: grid; grid-template-columns: 120px 1fr; gap: 4px 16px; padding: 12px 0;
         border-bottom: 1px solid var(--line); }}
.neighbors {{ grid-column: 1 / -1; display: flex; gap: 8px; flex-wrap: wrap; align-items: end; }}
figure {{ margin: 0; text-align: center; }}
figure.main svg {{ width: 120px; height: 120px; }}
figure.small svg {{ width: 56px; height: 56px; }}
figcaption {{ color: var(--muted); font-size: 12px; }}
svg .ink {{ fill: var(--ink); }} svg .frame {{ fill: none; stroke: var(--frame); }}
.char {{ font-size: 18px; }} .name {{ color: var(--muted); font-size: 12px; }}
.score {{ font-weight: 600; }} .score.dark {{ color: var(--dark); }} .score.light {{ color: var(--light); }}
.neighbors::before {{ content: "same reference position, fits well:"; color: var(--muted); font-size: 12px;
                      width: 100%; }}
</style>
</head>
<body>
<h1>{html.escape(target.font_id)}</h1>
<div class="meta">
  {len(deviations)} glyphs compared, {flagged} beyond ±3σ (σ = {comparison.residual_scale:.4f} coverage).
  Positions: {args.normalization}; tone curve: {html.escape(args.model)}. {len(comparison.predictions)} characters predicted but not in the font.<br>
  References ({len(refs)}, {f'within {args.max_darkness_ratio:g}× darkness' if args.max_darkness_ratio else 'no darkness limit'}): {reference_list}
</div>
{plot_svg(deviations, curve)}
<h2>Darker than expected</h2>
{cards(darker)}
<h2>Lighter than expected</h2>
{cards(lighter)}
</body>
</html>
'''


def glyph_svg(glyph: fb.Glyph | None) -> str:
    if glyph is None:
        return '<svg viewBox="0 0 1 1"></svg>'
    pen = SVGPathPen(None)
    glyph.draw(pen)
    frame = glyph.frame
    size = max(frame.width, frame.height)
    x = frame.x_min - (size - frame.width) / 2
    return (f'<svg viewBox="{x:.0f} {-frame.y_max - (size - frame.height) / 2:.0f} {size:.0f} {size:.0f}">'
            f'<rect class="frame" x="{frame.x_min:.0f}" y="{-frame.y_max:.0f}" width="{frame.width:.0f}" '
            f'height="{frame.height:.0f}" vector-effect="non-scaling-stroke"/>'
            f'<path class="ink" transform="scale(1,-1)" d="{pen.getCommands()}"/></svg>')


def plot_svg(deviations: list[fb.Deviation], curve: fb.ToneCurve) -> str:
    '''Coverage against reference position, with the tone curve; glyphs beyond ±3σ in color.'''
    width, height, pad = 1000, 360, 36
    x = np.array([d.position for d in deviations])
    y = np.array([d.actual for d in deviations])
    x0, x1 = x.min(), x.max()
    y0, y1 = 0.0, float(np.quantile(y, 0.999)) * 1.05

    def sx(v):
        return pad + (v - x0) / (x1 - x0) * (width - 2 * pad)

    def sy(v):
        return height - pad - (v - y0) / (y1 - y0) * (height - 2 * pad)

    def dots(selected) -> str:
        return ''.join(f'M{sx(d.position):.1f} {sy(d.actual):.1f}h1.6v1.6h-1.6z' for d in selected)

    grid = np.linspace(x0, x1, 200)
    line = ' '.join(f'{sx(a):.1f},{sy(b):.1f}' for a, b in zip(grid, curve.predict(grid)))
    normal = [d for d in deviations if abs(d.score) < 3]
    return f'''<svg class="plot" viewBox="0 0 {width} {height}" role="img" aria-label="Coverage against reference position">
<path d="{dots(normal)}" fill="var(--muted)" opacity="0.5"/>
<path d="{dots(d for d in deviations if d.score >= 3)}" fill="var(--dark)"/>
<path d="{dots(d for d in deviations if d.score <= -3)}" fill="var(--light)"/>
<polyline points="{line}" fill="none" stroke="var(--fg)" stroke-width="1.5"/>
<text x="{pad}" y="{height - 10}" fill="var(--muted)" font-size="12">reference position (lighter → darker)</text>
<text x="{pad}" y="20" fill="var(--muted)" font-size="12">coverage</text>
</svg>'''


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('font_id', nargs='?', help='A corpus font id, e.g. "OPPOSans Regular"')
    parser.add_argument('--font', type=Path, help='Any font file instead of a corpus font')
    parser.add_argument('--master', help='Master of --font (default: its default master)')
    parser.add_argument('--font-number', type=int, help='Font in a TTC/OTC collection')
    parser.add_argument('--exclude-group', help='With --font, a corpus design family to leave out of the references')
    parser.add_argument('--model', default='spline k5', choices=list(MODELS))
    parser.add_argument('--normalization', default='robust_z', choices=NORMALIZATIONS)
    parser.add_argument('--max-darkness-ratio', type=float, default=1.5,
                        help='Leave out references more than this factor darker or lighter than the target; 0 for '
                             'no limit (default: 1.5, see weight_bias.py)')
    parser.add_argument('--top', type=int, default=40, help='Glyphs to show in each direction')
    args = parser.parse_args()
    if (args.font_id is None) == (args.font is None):
        parser.error('Give either a corpus font id or --font.')
    return args


if __name__ == '__main__':
    main()
