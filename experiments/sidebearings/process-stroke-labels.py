# WARNING: hard-coded data intended to only be run once

import json
from collections import defaultdict

import pandas as pd
from glyphsLib import GSFont

from utils import read_side_bearings


print('Reading side bearing data...')
font = GSFont('3type-sy-9169字符_2.glyphs')
sb_data = read_side_bearings(font)

print('Reading excel file...')
df = pd.read_excel('树枝笔画标签综合.xlsx', header=None, usecols='A:F,H:M,O:U,W:AC')
label_data = defaultdict(lambda: {'left': [], 'right': [], 'top': [], 'bottom': []})

for i, row in df.iloc[2:].iterrows():
    left_data = row.iloc[0:6]
    right_data = row.iloc[6:12]
    top_data = row.iloc[12:19]
    bottom_data = row.iloc[19:26]

    # Left
    char = left_data.iloc[1]
    if not pd.isna(char): # Avoid empty subrow
        labels = left_data.iloc[3:5].dropna().tolist()
        assert all(label.startswith('左') for label in labels)
        labels = list(map(lambda label: label.lstrip('左').strip(), labels))
        label_data[char]['left'] = labels
        excel_sb = left_data.iloc[2]
        my_sb = sb_data['Regular'][char]['lsb']
        if excel_sb != my_sb:
            print(f'{char} (L): {excel_sb} != {my_sb}')

    # Right
    char = right_data.iloc[1]
    if not pd.isna(char): # Avoid empty subrow
        labels = right_data.iloc[3:5].dropna().tolist()
        assert all(label.startswith('右') for label in labels)
        labels = list(map(lambda label: label.lstrip('右').strip(), labels))
        label_data[char]['right'] = labels
        excel_sb = right_data.iloc[2]
        my_sb = sb_data['Regular'][char]['rsb']
        if excel_sb != my_sb:
            print(f'{char} (R): {excel_sb} != {my_sb}')

    # Top
    char = top_data.iloc[1]
    if not pd.isna(char): # Avoid empty subrow
        labels = top_data.iloc[3:6].dropna().tolist()
        assert all(label.endswith('顶') or label == '⺨' for label in labels)
        labels = list(map(lambda label: label if label == '⺨' else label[1:].rstrip('顶').strip(), labels))
        label_data[char]['top'] = labels
        excel_sb = top_data.iloc[2]
        my_sb = sb_data['Regular'][char]['tsb']
        if excel_sb != my_sb:
            print(f'{char} (T): {excel_sb} != {my_sb}')

    # Bottom
    char = bottom_data.iloc[1]
    if not pd.isna(char): # Avoid empty subrow
        labels = bottom_data.iloc[3:6].dropna().tolist()
        assert all(label.startswith('下') for label in labels)
        labels = list(map(lambda label: label.lstrip('下').strip(), labels))
        label_data[char]['bottom'] = labels
        excel_sb = bottom_data.iloc[2]
        my_sb = sb_data['Regular'][char]['bsb']
        if excel_sb != my_sb:
            print(f'{char} (B): {excel_sb} != {my_sb}')

output_filename = 'char-labels.json'
print(f'\nDone. Saving to "{output_filename}"...')
with open(output_filename, 'w') as f:
    json.dump(label_data, f)

valid_num = len(list(filter(lambda d: all(d.values()), label_data.values())))
print(f'Total number of recorded characters: {len(label_data)}.')
print(f'Number of characters with complete labels: {valid_num}.')
