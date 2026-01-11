import json
import argparse
from itertools import chain

from glyphsLib import GSFont
from pandas import DataFrame, ExcelWriter, MultiIndex
from tqdm import tqdm

from fontbench.utils import get_layer_by_master_name
from utils import read_side_bearings, get_outermost_range, get_outermost_strokes, dist_between_rankings


RANGE_COL_NAMES = {'lsb': '最左树枝笔画范围', 'rsb': '最右树枝笔画范围', 'tsb': '最上树枝笔画范围', 'bsb': '最下树枝笔画范围'}
LABEL_DIRECTION_TRANSLATE = {'lsb': 'left', 'rsb': 'right', 'tsb': 'top', 'bsb': 'bottom'}


def parse_args():
    parser = argparse.ArgumentParser(description='Process glyph side bearings data and output into an excel sheet.')

    parser.add_argument('-i', '--input-file', type=str, default='glyphs/3type-sy-9169字符_2.glyphs',
                        help='Path to the Glyphs file')
    parser.add_argument('--stroke-labels-file', type=str, default='char-labels.json',
                        help='Path to the stroke labels JSON file')
    parser.add_argument('--weights', nargs='+', default=['ExtraLight', 'Regular', 'Heavy'],
                        help='Font weights to process')
    parser.add_argument('-d', '--directions', nargs='+', default=['lsb', 'rsb', 'tsb', 'bsb'],
                        choices=['lsb', 'rsb', 'tsb', 'bsb', 'LSB', 'RSB', 'TSB', 'BSB'],
                        help='Directions to process (lsb, rsb, tsb, bsb)')
    parser.add_argument('-o', '--output-file', type=str, default='output/glyphs_data.xlsx',
                        help='Path to the output Excel file')
    parser.add_argument('--output-all-ranges', action='store_true', default=False,
                        help='Output all ranges for all directions')
    parser.add_argument('--debug', action='store_true', default=False,
                        help='Debug mode: will not output data to any file')
    return parser.parse_args()


args = parse_args()

print('Reading Glyphs file...')
font = GSFont(args.glyphs_file)
sb_data = read_side_bearings(font, weights=args.weights)
with open(args.stroke_labels_file) as f:
    char_labels = json.load(f)
# score = dist_between_rankings(sb_data, 'lsb')

# Populate main dataframe
print('Populating main dataframe...')
rows = []
for i, glyph in enumerate(tqdm(font.glyphs)):
    row = [glyph.id, glyph.string]
    if not args.output_all_ranges:
        labels = char_labels.get(glyph.string)
        glyph_labels = {}
        if labels is None:
            # Maybe we should notify this
            pass
        else:
            for direction in args.directions:
                strokes = labels.get(LABEL_DIRECTION_TRANSLATE[direction])
                if not strokes:
                    continue
                glyph_labels[direction] = True # Don't need to store strokes for now
                # glyph_labels[direction] = strokes
    for weight in args.weights:
        layer = get_layer_by_name(glyph, weight)
        glyph_sb = sb_data[weight].get(glyph.string) # TODO: key should be ID instead of string
        if glyph_sb is None:
            row += [None] * len(args.directions) * 3
            continue
        row += list(map(lambda direction: glyph_sb[direction], args.directions))
        # Output all ranges of all directions
        if args.output_all_ranges:
            row += list(chain(*map(lambda direction: get_outermost_range(layer, direction)[0], args.directions)))
            continue
        # Output only ranges which correspond to directions with branch strokes
        for direction in args.directions:
            if glyph_labels.get(direction):
                row += get_outermost_range(layer, direction)[0]
            else:
                row += [None] * 2
    rows.append(row)

columns = ['ID', '字符']
for weight in args.weights:
    for direction in args.directions:
        columns.append(f'{weight}-{direction}')
    for direction in args.directions:
        columns.append(f'{weight}-{direction}-range1')
        columns.append(f'{weight}-{direction}-range2')
df = DataFrame(rows, columns=columns)
df['ID'] = df['ID'].astype(str)
df['字符'] = df['字符'].astype(str)


# Populate dataframes for stroke sheets
print('Populating strokes dataframe...')
stroke_dfs = {}
for direction in args.directions:
    label_direction = LABEL_DIRECTION_TRANSLATE[direction]
    relevant_glyphs = list(filter(lambda g: char_labels.get(g.string, {}).get(label_direction), font.glyphs))
    
    rows = []
    for i, glyph in enumerate(tqdm(relevant_glyphs)):
        row = [glyph.id, glyph.string]
        row.append(' '.join(char_labels[glyph.string][label_direction]))
        for weight in args.weights:
            glyph_sb = sb_data[weight].get(glyph.string, {}).get(direction)
            if glyph_sb is None:
                row += [None] * 4
                continue
            row.append(glyph_sb)
            layer = get_layer_by_name(glyph, weight)
            row.append(len(get_outermost_strokes(layer, direction)[0]))
            row += get_outermost_range(layer, direction)[0]
        rows.append(row)
    
    columns = ['ID', '字符', '标签']
    for weight in args.weights:
        columns += map(lambda s: f'{weight}-{s}', [direction.upper(), '字形外侧笔画数', '范围起始', '范围结束'])
    stroke_df = DataFrame(rows, columns=columns)

    stroke_df.sort_values(by='标签', inplace=True)
    stroke_dfs[direction] = stroke_df

if args.debug:
    print('Done.')
    exit()

print('Exporting to excel file...')
writer = ExcelWriter(args.output_file, engine='xlsxwriter')
book = writer.book
header_format = book.add_format({'align': 'center', 'valign': 'vcenter', 'bold': True, 'border': 0})
vcenter_format = book.add_format({'valign': 'vcenter'})
# border_format = book.add_format({'right': 2})

### Main Sheet
sheet = book.add_worksheet('全字符数据')
sheet.set_default_row(18)
writer.sheets['全字符数据'] = sheet
df.to_excel(writer, sheet_name='全字符数据', index=False, startrow=1)

sheet.merge_range('A1:A2', columns[0], header_format)
sheet.merge_range('B1:B2', columns[1], header_format)
for i, weight in enumerate(args.weights):
    weight_col = 2 + i * len(args.directions) * 3
    sheet.merge_range(0, weight_col, 0, weight_col + len(args.directions) * 3 - 1, weight, header_format)
    for j, direction in enumerate(args.directions):
        sheet.write(1, weight_col + j, args.directions[j].upper())
        dir_col = weight_col + len(args.directions) + j * 2
        col_name = RANGE_COL_NAMES[direction]
        sheet.merge_range(1, dir_col, 1, dir_col + 1, col_name, header_format)
sheet.set_row(0, 30, header_format)
sheet.set_row(1, 30, header_format)
sheet.set_column('A:XFD', None, vcenter_format)

### Strokes Sheets
for direction in args.directions:
    sheet_name = RANGE_COL_NAMES[direction].rstrip('范围').lstrip('最') + '数据'
    sheet = book.add_worksheet(sheet_name)
    sheet.set_default_row(18)
    writer.sheets[sheet_name] = sheet
    stroke_dfs[direction].to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)

    sheet.merge_range('A1:A2', columns[0], header_format)
    sheet.merge_range('B1:B2', columns[1], header_format)
    sheet.merge_range('C1:C2', columns[2], header_format)
    for i, weight in enumerate(args.weights):
        weight_col = 3 + i * 4
        sheet.merge_range(0, weight_col, 0, weight_col + 3, weight, header_format)
        for j in range(4):
            col_name = stroke_dfs[direction].columns[weight_col + j].replace(f'{weight}-', '')
            sheet.write(1, weight_col + j, col_name)
    sheet.set_row(0, 30, header_format)
    sheet.set_row(1, 30, header_format)
    sheet.set_column('A:XFD', None, vcenter_format)

writer.close()
print('Done.')

# fixed_columns = ['ID', '字符']
# weight_columns = [d.upper() for d in args.directions] + list(chain([f'{d}-range1', f'{d}-range2'] for d in args.directions))
# data_columns = MultiIndex.from_product([args.weights, weight_columns], names=['weight', 'metric'])
