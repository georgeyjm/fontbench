from glyphsLib import GSFont
from tqdm import tqdm

import fontbench.metrics as m


def test_grayscale_new_method(font: GSFont):
    progress = tqdm(len(font.glyphs) * len(font.glyphs[0].layers))
    for glyph in font.glyphs:
        for layer in glyph.layers:
            progress.update(1)
            test = m.grayscale(layer, 'integration')
            reference = m.grayscale(layer)
            if abs(test - reference) > 1e-2:
                print(f'Layer "{layer.name}" of glyph "{glyph.id}" ("{glyph.string or glyph.unicode}") has a difference of {abs(test - reference)}')
                print(f'Test: {test}, Reference: {reference}')
                print(f'Layer width: {layer.width}, Layer vertWidth: {layer.vertWidth}')
                print('--------------------------------')
