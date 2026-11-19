from typing import Literal

from fontTools.pens.basePen import AbstractPen
from fontTools.pens.statisticsPen import StatisticsPen
from glyphsLib import GSLayer

from fontbench.font_proxy import GlyphProxy
from fontbench.utils import layer_to_svg, get_layer_height
from fontbench.integration import area_of_paths, svg_to_paths


def grayscale(glyph: GSLayer | GlyphProxy, method: Literal['statistics', 'integration'] = 'statistics') -> float:
    '''
    Calculates the grayscale (float in the range [0, 1]) of a glyph: its ink area divided by the area of
    its box (advance width x ascender-to-descender).

    Methods:
        statistics: Exact area from fontTools' StatisticsPen, with overlapping contours merged first.
        integration: Numerical integration along the outline. Only supports glyph layers, and counts
            overlapping contours twice.
    '''
    if method == 'statistics':
        width, height = _glyph_box(glyph)
        if width * height == 0:
            raise ValueError('Glyph has zero width or height.')
        return abs(outline_statistics(glyph).area) / (width * height)
    elif method == 'integration':
        if not isinstance(glyph, GSLayer):
            raise TypeError('The integration method only supports glyph layers.')
        return _layer_grayscale_integration(glyph)
    raise ValueError(f'Unknown method: {method}')


def outline_statistics(glyph: GSLayer | GlyphProxy, remove_overlaps: bool = True) -> StatisticsPen:
    '''
    Returns a StatisticsPen that has drawn the glyph's outline, with components decomposed.
    Besides `area`, it holds the ink's center of mass (`meanX`, `meanY`), spread (`stddevX`, `stddevY`),
    `correlation` and `slant`, all in font units.

    StatisticsPen counts overlapping areas once per contour covering them, so by default overlaps are merged
    first with skia-pathops. The sign of `area` depends on contour direction; use its absolute value.
    '''
    glyph_set = glyph.master.glyphs if isinstance(glyph, GlyphProxy) else _LayerGlyphSet(glyph)
    stats_pen = StatisticsPen(glyphset=glyph_set)
    if not remove_overlaps:
        _draw(glyph, stats_pen)
        return stats_pen

    from pathops import Path, PathPen

    path = Path()
    _draw(glyph, PathPen(path, glyphSet=glyph_set))
    path.simplify(fix_winding=True)
    path.draw(stats_pen)
    return stats_pen


def lightness(coverage: float) -> float:
    '''
    Converts ink coverage (in [0, 1]) to CIE L* perceptual lightness (100 = blank paper, 0 = solid black).

    The glyph is treated as a flat patch whose relative luminance is the fraction of paper left uncovered.
    Equal differences in L* look like roughly equal differences in darkness, which is not true of raw coverage.
    '''
    if not 0.0 <= coverage <= 1.0:
        raise ValueError(f'Coverage must be in [0, 1], got {coverage}.')
    luminance = 1.0 - coverage
    if luminance > (6 / 29) ** 3:
        return 116 * luminance ** (1 / 3) - 16
    return (29 / 3) ** 3 * luminance


class _LayerGlyphSet:
    '''
    Minimal glyph set resolving component names to the layers of the same master, so pens can decompose them.
    '''

    def __init__(self, layer: GSLayer):
        self.font = layer.parent.parent
        self.master_id = layer.associatedMasterId

    def __getitem__(self, glyph_name: str) -> GSLayer:
        return self.font.glyphs[glyph_name].layers[self.master_id]


def _draw(glyph: GSLayer | GlyphProxy, pen: AbstractPen) -> None:
    if isinstance(glyph, GlyphProxy):
        glyph.glyph.draw(pen)
    else:
        glyph.draw(pen)


def _glyph_box(glyph: GSLayer | GlyphProxy) -> tuple[float, float]:
    if isinstance(glyph, GlyphProxy):
        return glyph.width, glyph.height
    return glyph.width, get_layer_height(glyph)


def _layer_grayscale_integration(layer: GSLayer, samples_per_segment: int = 20) -> float:
    width = layer.width
    height = get_layer_height(layer)
    paths = svg_to_paths(layer_to_svg(layer, full_svg=False))
    area = abs(area_of_paths(paths, samples_per_segment))
    return area / (width * height)
