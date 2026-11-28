'''
The 黑体 corpus for validating reference grayscale: which fonts and masters, grouped by design family, and a cache
of their measurements.

Fonts are read from ../各种黑体大全, outside the repo. Measure everything not cached yet with

    python experiments/validation/corpus.py

and use load_corpus() in other scripts. Fonts are measured over the 9169 set and the whole 通用规范汉字表.

Left out: the duplicate/ folder (copies of 字体/), the byte-identical "(1)" copies of the 华康 fonts, DFT_C5.TTC
(fontTools rejects its cmap), and the HK/TC members and hidden "." members of the PingFang, Hiragino and STHeiti
collections.
'''

from __future__ import annotations

import math
import pickle
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
from tqdm import tqdm

import fontbench as fb


REPO = Path(__file__).resolve().parents[2]
FONT_ROOT = REPO.parent / '各种黑体大全'
CACHE = Path(__file__).parent / 'data' / 'corpus.pickle'
CHARS = fb.chars_9169() | fb.tongyong_guifan(1, 2, 3)
_CHAR_ORDER = sorted(CHARS)
# Fewest shared non-empty glyphs for comparing two fonts' darkness
MIN_SHARED = 20


@dataclass(frozen=True)
class Source:
    '''One font file, or one font of a collection.'''
    path: str
    # Design family. Fonts sharing a design (weights, versions, 简体 and Pro releases) are left out together, so a
    # font is never judged against a sibling of itself.
    group: str
    font_number: int | None = None
    # 'TC' fonts use traditional character forms for shared code points and stay out of SC references
    region: str = 'SC'
    note: str = ''


@dataclass(frozen=True)
class CorpusFont:
    source: Source
    measurement: fb.FontMeasurement

    @property
    def font_id(self) -> str:
        return self.measurement.font_id

    @property
    def group(self) -> str:
        return self.source.group

    @property
    def region(self) -> str:
        return self.source.region

    @cached_property
    def shape(self) -> fb.ShapeSummary:
        '''Distribution over level 1 of the 通用规范汉字表; shape.median is the font's overall darkness.'''
        return fb.shape_summary(self.measurement)

    @cached_property
    def log_coverage(self) -> np.ndarray:
        '''Log coverage of each character of CHARS, in code point order; NaN where missing or empty.'''
        by_char = self.measurement.by_char
        coverage = [by_char[c].coverage if c in by_char else np.nan for c in _CHAR_ORDER]
        with np.errstate(divide='ignore'):
            values = np.log(np.array(coverage, dtype=float))
        values[~np.isfinite(values)] = np.nan
        return values


def relative_darkness(font: CorpusFont, target: CorpusFont) -> float:
    '''
    log(font's darkness / target's darkness): the median, over the characters both fonts have, of the log ratio
    of their coverages.

    Comparing on shared characters matters for partial fonts. A work-in-progress font of 300 mostly simple glyphs
    has a much lower median coverage than the finished font will, so judging it by its own median (shape.median)
    makes it look up to a quarter lighter, and it gets references that are too light. On the same characters the
    ratio is unbiased. Mean, median and geometric mean of the per-character ratios, and the ratio of medians, were
    equally accurate on partial fonts; the median was slightly better on complete ones and ignores odd glyphs.
    '''
    differences = font.log_coverage - target.log_coverage
    shared = differences[~np.isnan(differences)]
    if len(shared) < MIN_SHARED:
        raise ValueError(f'{font.font_id} and {target.font_id} share only {len(shared)} non-empty glyphs.')
    return float(np.median(shared))


def reference_fonts(
    target: CorpusFont,
    corpus: list[CorpusFont],
    mode: str = 'matched',
    max_darkness_ratio: float | None = 1.5,
    min_references: int = 3,
) -> list[CorpusFont]:
    '''
    Reference fonts for a target, never from the target's own design family.

    Modes:
        matched: from each other family, the master closest to the target in overall darkness.
        all: every master of every other family (families with many weights then count many times).
    max_darkness_ratio: drop references darker or lighter than the target by more than this factor; None keeps
        them all. The default of 1.5 comes from weight_bias.py: very light targets otherwise get mostly mid-weight
        references, and their dense glyphs are predicted about 2.7% too light. 1.5× was never worse than no limit
        for light, mid or heavy targets.
    min_references: if the limit leaves fewer than this many, keep this many closest in darkness instead. The
        lightest corpus masters keep just 3 references at 1.5×, so a still lighter target could keep none.
    '''
    others = [f for f in corpus if f.group != target.group]
    if mode == 'matched':
        by_group: dict[str, list[CorpusFont]] = {}
        for f in others:
            by_group.setdefault(f.group, []).append(f)
        others = [min(fonts, key=lambda f: _darkness_distance(f, target)) for fonts in by_group.values()]
    elif mode != 'all':
        raise ValueError(f'Unknown mode {mode!r}')
    if max_darkness_ratio is not None:
        limit = math.log(max_darkness_ratio)
        within = [f for f in others if _darkness_distance(f, target) <= limit]
        if len(within) < min_references:
            within = sorted(others, key=lambda f: _darkness_distance(f, target))[:min_references]
        others = within
    return others


def _darkness_distance(font: CorpusFont, target: CorpusFont) -> float:
    return abs(relative_darkness(font, target))


def _files(group: str, folder: str, names: list[str]) -> list[Source]:
    return [Source(f'{folder}/{name}', group) for name in names]


SOURCES: list[Source] = [
    Source('OPPO Sans 4.0.ttf', 'OPPO Sans', note='variable'),
    Source('字体/OPPOSans-R.ttf', 'OPPO Sans', note='earlier static release'),
    Source('SmaGoSSNew01272014CN-Regular.otf', 'SmaGoSS'),
    Source('TPTQHeiTC-Regular.ttf', 'TPTQ 黑', region='TC'),
    *_files('IBM Plex Sans SC', 'ibm-plex-sans-sc', [
        f'IBMPlexSansSC-{w}.otf' for w in ('Thin', 'ExtraLight', 'Light', 'Regular', 'Text', 'Medium', 'SemiBold', 'Bold')
    ]),
    *_files('华康UD黑', '华康UD黑', ['华康UD黑 Std W4.otf', '华康UD黑 Std W6.otf']),
    *_files('华康青花黑', '华康青花黑W1-7', [f'华康青花黑 Std W{w}.otf' for w in range(1, 8)]),
    Source('字体/AdobeHeitiStd-Regular.otf', 'Adobe 黑体'),
    Source('字体/Alibaba-PuHuiTi-Regular.otf', '阿里巴巴普惠体'),
    Source('字体/AritaHeiti-Medium-170509-01.otf', '阿丽达黑体'),
    Source('字体/FZHTJW.TTF', '方正黑体'),
    Source('字体/FZLTHJW.otf', '方正兰亭黑'),
    *_files('方正兰亭黑', '方正兰亭黑Pro', [
        f'FZLTHPro_GB18030{w}.otf' for w in ('_Xian', '_Xi', '', '_Zhun', '_Zhong', '_ZhongCu', '_Cu', '_Da', '_Te')
    ]),
    Source('字体/FZXDXJW.TTF', '方正细等线'),
    Source('字体/FZXH1JW.TTF', '方正细黑一'),
    Source('字体/FZXH-GB18030.ttf', '方正细黑一', note='GB18030 release'),
    Source('字体/FZYouH_503L.ttf', '方正悠黑'),
    Source('字体/方正韵动中黑简.TTF', '方正韵动黑'),
    *_files('方正德赛黑', '方正德赛黑', [
        f'FZDeSHJW_{w}.TTF' for w in ('501L', '502L', '503L', '504L', '505L', '506L', '507R', '508R', '509R', '510M',
                                       '511M', '512B')
    ]),
    Source('字体/GEETYPE信黑简 W4(GEETYPE-XinGothicGB-W4).ttf', 'GEETYPE 信黑'),
    *_files('汉仪简黑', '字体', ['HYXiJianHeiJ.ttf', 'HYZhongJianHeiJ.ttf', 'HYCuJianHeiJ.ttf']),
    *_files('汉仪等线', '字体', ['HYXiDengXianJ.ttf', 'hyg2gjm.ttf']),
    Source('字体/HYQiHei-55J.ttf', '汉仪旗黑'),
    Source('字体/HYYuanLongHei-35J.ttf', '汉仪元隆黑'),
    Source('字体/HYZhongHeiJ.ttf', '汉仪中黑'),
    Source('字体/HarmonyOS_Sans_SC_Regular.ttf', 'HarmonyOS Sans'),
    Source('字体/Hiragino Sans GB.ttc', '冬青黑体', font_number=0),
    Source('字体/Hiragino Sans GB.ttc', '冬青黑体', font_number=2),
    Source('字体/MHeiPRC-Medium.OTF', 'M 黑'),
    Source('字体/MXiangHeHeiSCStd-Regular.otf', 'M 翔鹤黑'),
    Source('字体/MYingHeiPRC-W5.otf', 'M 盈黑'),
    Source('字体/MYuenPRC-SemiBold.OTF', 'M 圆', note='rounded'),
    Source('字体/MiSans-Regular.ttf', 'MiSans'),
    Source('字体/Ping Hei Text.ttf', 'Ping Hei'),
    *[Source('字体/PingFang.ttc', '苹方', font_number=n) for n in (17, 14, 11, 2, 5, 8)],
    Source('字体/STHeiti Light.ttc', '华文黑体', font_number=1),
    Source('字体/SourceHanSansSC-Normal.otf', '思源黑体'),
    Source('字体/gcsh00m.ttf', '文鼎晶栩黑'),
    *_files('文鼎黑体', '字体', ['ghei00m.ttf', 'ghei00b.ttf']),
    Source('字体/gjxh00m.ttf', '文鼎UD晶熙黑'),
    Source('字体/gslh00l.ttf', '文鼎书林黑'),
    Source('字体/iLiHei.ttf', 'iLiHei'),
    Source('字体/msjh.ttf', '微软正黑', region='TC'),
]


def _key(source: Source, master: str) -> str:
    return f'{source.path}#{source.font_number}#{master}'


def _read_cache() -> dict[str, fb.FontMeasurement]:
    if not CACHE.is_file():
        return {}
    with CACHE.open('rb') as f:
        return pickle.load(f)


def load_corpus(region: str | None = 'SC') -> list[CorpusFont]:
    '''All cached font masters, in SOURCES order; only one region's fonts unless region is None.'''
    cache = _read_cache()
    if not cache:
        raise FileNotFoundError(f'{CACHE} is missing; run python experiments/validation/corpus.py first.')
    corpus = []
    for source in SOURCES:
        if region is not None and source.region != region:
            continue
        prefix = _key(source, '')
        corpus += [CorpusFont(source, m) for key, m in cache.items() if key.startswith(prefix)]
    font_ids = [f.font_id for f in corpus]
    duplicates = {i for i in font_ids if font_ids.count(i) > 1}
    if duplicates:
        raise ValueError(f'Font ids are not unique: {duplicates}')
    return corpus


def measure_corpus() -> None:
    '''Measures every master of every source that is not in the cache yet, saving after each font.'''
    cache = _read_cache()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        font = fb.open_font(FONT_ROOT / source.path, source.font_number)
        for master in font.masters:
            key = _key(source, master)
            if key in cache:
                continue
            m = fb.measure_font(font, master, chars=CHARS,
                                progress=lambda items: tqdm(items, desc=f'{font.family} {master}', unit=' glyphs',
                                                            leave=False))
            cache[key] = m
            print(f'{m.font_id}: measured {len(m)}')
        with CACHE.open('wb') as f:
            pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)


if __name__ == '__main__':
    measure_corpus()
