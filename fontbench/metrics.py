from fontTools.pens.statisticsPen import StatisticsPen

from fontbench.sources import Glyph


def outline_statistics(glyph: Glyph, remove_overlaps: bool = True) -> StatisticsPen:
    '''
    Returns a StatisticsPen that has drawn the glyph's outline. Besides `area`, it holds the ink's center of
    mass (`meanX`, `meanY`), spread (`stddevX`, `stddevY`), `correlation` and `slant`, all in font units.

    StatisticsPen counts an area once for every contour covering it, so by default overlapping contours are
    merged first (with skia-pathops). The sign of `area` depends on contour direction; use its absolute value.
    '''
    stats_pen = StatisticsPen()
    if not remove_overlaps:
        glyph.draw(stats_pen)
        return stats_pen

    from pathops import Path, PathPen

    path = Path()
    glyph.draw(PathPen(path))
    path.simplify(fix_winding=True)
    path.draw(stats_pen)
    return stats_pen


def coverage(glyph: Glyph) -> float:
    '''
    Ink area divided by the area of the glyph's frame (advance width x descender-to-ascender), with overlaps
    counted once. Usually in [0, 1]; ink outside the frame is still counted.
    '''
    frame_area = glyph.frame.area
    if frame_area <= 0:
        raise ValueError(f'Glyph "{glyph.name}" has an empty frame.')
    return abs(outline_statistics(glyph).area) / frame_area


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
