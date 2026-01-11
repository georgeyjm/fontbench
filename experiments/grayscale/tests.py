from glyphsLib import GSFont
from tqdm import tqdm

from main import occupancy_ratio_from_svg, occupancy_ratio_reference
from integration import layer_to_svg, get_layer_height


def test_grayscale_new_method(font: GSFont):
    progress = tqdm(len(font.glyphs) * len(font.glyphs[0].layers))
    for glyph in font.glyphs:
        for layer in glyph.layers:
            progress.update(1)
            svg_code = layer_to_svg(layer)
            svg_path = layer_to_svg(layer, full_svg=False)
            test = occupancy_ratio_from_svg(svg_path, layer.width, get_layer_height(layer))
            reference = occupancy_ratio_reference(svg_code)
            if abs(test - reference) > 1e-2:
                print(f'Glyph {glyph.string} has a difference of {abs(test - reference)}')
                print(f'Test: {test}, Reference: {reference}')
                print(f'SVG code: {svg_code}')
                print(f'SVG path: {svg_path}')
                print(f'Layer width: {layer.width}, Layer vertWidth: {layer.vertWidth}')
                print('--------------------------------')
