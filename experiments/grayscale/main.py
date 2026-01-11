import json
import pickle
import argparse
from pathlib import Path

from glyphsLib import GSFont
import numpy as np
import pyvips
from tqdm import tqdm

from fontbench.utils import layer_to_svg
from integration import occupancy_ratio, svg_to_paths


def read_input_font(input_path: Path) -> GSFont:
    '''
    Read the input file (raw Glyphs file or parsed pickle file) and return the GSFont object.
    '''
    if not input_path.is_file():
        raise FileNotFoundError(f'File not found: {input_path}')
    if input_path.suffix == '.glyphs':
        if (pkl_file := input_path.with_suffix('.pickle')).is_file() or (pkl_file := input_path.with_suffix('.pkl')).is_file():
            response = input('Corresponding pickle file found. Use pickle file instead? [(y)/n]')
            if response.lower().strip() in ('y', 'yes', ''):
                return pickle.load(pkl_file.open('rb'))
        print('Reading Glyphs file...')
        font = GSFont(input_path)
        print('Done.')
        response = input('Save the parsed font as a pickle file? [(y)/n]')
        if response.lower().strip() in ('y', 'yes', ''):
            save_path = input_path.with_suffix('.pickle')
            pickle.dump(font, save_path.open('wb'))
            print(f'Saved parsed font at {save_path}')
        return font
    elif input_path.suffix in ('.pickle', '.pkl'):
        return pickle.load(input_path.open('rb'))
    else:
        raise ValueError(f'Unsupported file extension: {input_path.suffix}')


def process_glyphs_grayscale(font: GSFont) -> list[dict]:
    print('Calculating glyphs grayscale...')
    data = []
    progress = tqdm(total=sum(len(glyph.layers) for glyph in font.glyphs))
    for glyph in font.glyphs:
        glyph_data = {'id': glyph.id, 'string': glyph.string, 'unicode': glyph.unicode, 'grayscale': {}}
        for layer in glyph.layers:
            progress.update(1)
            svg_code = layer_to_svg(layer)
            grayscale = occupancy_ratio_reference(svg_code)
            glyph_data['grayscale'][layer.master.name] = grayscale
        data.append(glyph_data)
    return data


def occupancy_ratio_from_svg(svg_code: str, width_px: int, height_px: int, samples_per_segment: int = 10) -> float:
    return occupancy_ratio(svg_to_paths(svg_code), width_px, height_px, samples_per_segment)


def occupancy_ratio_reference(svg_code: str) -> float:
    # Convert SVG code to NumPy array
    im = pyvips.Image.svgload_buffer(bytes(svg_code, 'utf-8'), scale=1.0)
    arr = (255 - im.numpy()[:, :, 0]) / 255
    height, width = arr.shape
    total_sum = arr.sum()

    return (total_sum / (width * height)).item()


def parse_args():
    parser = argparse.ArgumentParser(description='')

    parser.add_argument('-i', '--input', type=Path, required=True, help='Path to the Glyphs/pickle/JSON file')
    parser.add_argument('--json', type=Path, help='Path to save the processed grayscale data as a JSON file')
    parser.add_argument('--jsonl', type=Path, help='Path to save the processed grayscale data as a JSONL file')
    # parser.add_argument('--stroke-labels-file', type=str, default='char-labels.json',
    #                     help='Path to the stroke labels JSON file')
    # parser.add_argument('--weights', nargs='+', default=['ExtraLight', 'Regular', 'Heavy'],
    #                     help='Font weights to process')
    # parser.add_argument('-d', '--directions', nargs='+', default=['lsb', 'rsb', 'tsb', 'bsb'],
    #                     choices=['lsb', 'rsb', 'tsb', 'bsb', 'LSB', 'RSB', 'TSB', 'BSB'],
    #                     help='Directions to process (lsb, rsb, tsb, bsb)')
    # parser.add_argument('-o', '--output-file', type=str, default='output/glyphs_data.xlsx',
    #                     help='Path to the output Excel file')
    # parser.add_argument('--output-all-ranges', action='store_true', default=False,
    #                     help='Output all ranges for all directions')
    # parser.add_argument('--debug', action='store_true', default=False,
    #                     help='Debug mode: will not output data to any file')
    return parser.parse_args()


args = parse_args()

if args.input.suffix.lower() in ('.glyphs', '.pickle', '.pkl'):
    font = read_input_font(args.input)
    data = process_glyphs_grayscale(font)
    if args.json and not args.json.exists():
        with open(args.json, 'w') as f:
            json.dump(data, f, indent=4)
        print(f'Saved processed grayscale data at {args.json}')
    if args.jsonl and not args.jsonl.exists():
        with open(args.jsonl, 'w') as f:
            for item in data:
                f.write(json.dumps(item) + '\n')
        print(f'Saved processed grayscale data at {args.jsonl}')
elif args.input.suffix.lower() == '.json':
    with open(args.input, 'r') as f:
        data = json.load(f)
elif args.input.suffix.lower() == '.jsonl':
    with open(args.input, 'r') as f:
        data = [json.loads(line) for line in f]
