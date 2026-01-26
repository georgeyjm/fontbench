import json

import pyvips

from fontbench import FontProxy


font = FontProxy('各种黑体大全/OPPO Sans 4.0.ttf')
json_file = 'experiments/grayscale/data/OPPO Sans 4.0.jsonl'
data = {}
with open(json_file) as f:
    for line in f:
        line = json.loads(line)
        data[line['id']] = line

for glyph in font.iter_glyphs():
    svg_code = glyph.to_svg_code()
    try:
        im = pyvips.Image.svgload_buffer(bytes(svg_code, 'utf-8'), scale=1.0)
    except Exception as e:
        if glyph.width == 0 or glyph.height == 0:
            continue
        print(f'Error loading SVG for glyph {glyph.glyph_id}: {e}')
        continue
    arr = im.numpy()[:, :, 3]
    height, width = arr.shape
    total_sum = arr.sum().item()
    calculated_grayscale = total_sum / (width * height) / 255
    
    glyph_data = data[glyph.glyph_id]
    master_name = glyph.master.name
    if master_name not in glyph_data['grayscale']:
        continue
    assert glyph.string == glyph_data['string']
    if calculated_grayscale == 0:
        # print(f'{glyph.glyph_id} ({master_name}): {calculated_grayscale} == 0')
        continue
    if (calculated_grayscale - glyph_data['grayscale'][master_name]) / calculated_grayscale > 0.01:
        print(f'{glyph.glyph_id} ({master_name}): {calculated_grayscale} != {glyph_data['grayscale'][master_name]}')
