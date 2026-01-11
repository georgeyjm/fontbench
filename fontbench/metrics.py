from typing import Literal

from glyphsLib import GSLayer
import numpy as np

from fontbench.utils import layer_to_svg, get_layer_height
from fontbench.integration import area_of_paths, svg_to_paths


def grayscale(layer: GSLayer, method: Literal['integration', 'pyvips'] = 'pyvips') -> float:
    '''
    Calculates the grayscale (float in the range [0, 1]) of a glyph layer.
    '''
    if method == 'integration':
        return _layer_grayscale_integration(layer)
    elif method == 'pyvips':
        return _layer_grayscale_pyvips(layer)


def _layer_grayscale_pyvips(layer: GSLayer) -> float:
    '''
    Calculates the grayscale of a glyph layer by rasterizing the SVG using pyvips and summing pixels.
    '''
    import pyvips

    svg_code = layer_to_svg(layer)
    im = pyvips.Image.svgload_buffer(bytes(svg_code, 'utf-8'), scale=1.0)
    arr = 255 - im.numpy()[:, :, 0]
    height, width = arr.shape
    total_sum = arr.sum().item()

    return total_sum / (width * height) / 255


def _layer_grayscale_integration(layer: GSLayer, samples_per_segment: int = 20) -> float:
    width = layer.width
    height = get_layer_height(layer)
    paths = svg_to_paths(layer_to_svg(layer, full_svg=False))
    area = abs(area_of_paths(paths, samples_per_segment))
    return area / (width * height)
