import numpy as np


def glyph_grayscale(glyph, method='integration') -> float:
    '''
    Calculates the grayscale (float in the range [0, 1]) of a glyph.
    '''
    assert method in ('integration', 'pyvips')
    if method == 'integration':
        return _glyph_grayscale_integration()
    elif method == 'pyvips':
        import pyvips
        return _glyph_grayscale_pyvips()

def _glyph_grayscale_pyvips(glyph) -> float:
    '''
    Calculates the grayscale of a glyph by rasterizing the SVG using pyvips and summing pixels.
    '''
    svg_code = None
    # im = pyvips.Image.svgload_buffer(bytes(svg_code, 'utf-8'), scale=1.0)
    im = pyvips.Image.svgload_buffer(svg_code, scale=1.0)
    arr = 255 - im.numpy()[:, :, 0]
    height, width = arr.shape
    total_sum = arr.sum()

    return total_sum / (width * height) / 255

def _glyph_grayscale_integration(glyph) -> float:
    return 0.0
