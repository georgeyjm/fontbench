import random
import itertools
from functools import lru_cache

import numpy as np
from scipy import stats
from glyphsLib import GSGlyph, GSLayer, GSPath, GSComponent
from glyphsLib import LINE, CURVE, QCURVE, OFFCURVE


@lru_cache
def get_glyph(font, char):
    for glyph in font.glyphs:
        if char in (glyph.string, glyph.id):
            return glyph


@lru_cache
def get_layer_by_name(glyph, layer_name):
    for layer in glyph.layers:
        if layer_name == layer.name:
            return layer


def read_side_bearings(font, weights=('ExtraLight','Regular','Black')):
    # Get baseline offset and height data
    baseline = {}
    height = {}
    for master in font.masters:
        if master.name not in weights:
            continue
        baseline[master.name] = master.descender
        height[master.name] = master.ascender - master.descender

    # Get side bearing data of all glyphs
    data = {weight: {} for weight in weights}
    for glyph in font.glyphs:
        for layer in glyph.layers:
            master_name = layer.master.name
            if master_name not in weights:
                continue 
            if layer.bounds is None:
                # Not drawn yet
                continue
            lsb = layer.bounds.origin.x
            rsb = layer.width - lsb - layer.bounds.size.width
            bsb = layer.bounds.origin.y - baseline[master_name]
            tsb = height[master_name] - bsb - layer.bounds.size.height
            data[master_name][glyph.string] = {'id': glyph.id, 'lsb': lsb, 'rsb': rsb, 'bsb': bsb, 'tsb': tsb}
        # for tag in glyph.tags:
        #     print(tag)
    return data


def dist_between_rankings(sb_data, direction):
    direction = direction.lower()
    assert direction in ('lsb', 'rsb', 'tsb', 'bsb')

    # Calculates Kendall's tau as a measure of distance between two rankings
    # An alternative to consider is Rank Biased Overlap (RBO)
    # IMPORTANT: We calculate Kendall's tau between ALL pairs of rankings.
    # This is to accommodate for one odd ranking in the middle having too much impact on the overall score.
    weights = list(sb_data.keys())
    if len(weights) == 1:
        return 1
    scores = []
    common_chars = list(set.intersection(*[set(sb_data[weight].keys()) for weight in weights])) # List is important to guarantee stable sort
    for weight1, weight2 in itertools.combinations(weights, 2): # Can shorten to combining weights.values()
        ranking1 = sorted(common_chars, key=lambda char: sb_data[weight1][char][direction])
        ranking2 = sorted(common_chars, key=lambda char: sb_data[weight2][char][direction])
        tau = stats.kendalltau(ranking1, ranking2)
        scores.append((weight1, weight2, tau.statistic))
    return scores, ranking1, ranking2


def dist_between_rankings_random_batches(sb_data, direction, batch_size=50, samples=100):
    direction = direction.lower()
    assert direction in ('lsb', 'rsb', 'tsb', 'bsb')

    # Calculates Kendall's tau as a measure of distance between two rankings
    # An alternative to consider is Rank Biased Overlap (RBO)
    # IMPORTANT: We calculate Kendall's tau between ALL pairs of rankings.
    # This is to accommodate for one odd ranking in the middle having too much impact on the overall score.
    weights = list(sb_data.keys())
    if len(weights) == 1:
        return 1
    scores = []
    common_chars = list(set.intersection(*[set(sb_data[weight].keys()) for weight in weights])) # List is important to guarantee stable sort
    for i in range(samples):
        batch = random.choices(common_chars, k=batch_size) # Should we consider non-replacement?
        batch_scores = []
        for weight1, weight2 in itertools.combinations(weights, 2): # Can shorten to combining weights.values()
            ranking1 = sorted(batch, key=lambda char: sb_data[weight1][char][direction])
            ranking2 = sorted(batch, key=lambda char: sb_data[weight2][char][direction])
            tau = stats.kendalltau(ranking1, ranking2)
            batch_scores.append(tau.statistic)
        scores.append(batch_scores)
    # Calculate mean scores
    scores = list(map(lambda s: sum(s) / len(s), zip(*scores)))
    return scores


def compare_node_to_record(node, record, direction):
    coord = get_coord_at_direction(node, direction)
    if record is None:
        return 1, coord
    if direction in ('lsb', 'bsb'):
        if coord < record:
            return 1, coord
        elif coord == record:
            return 0, record
        return -1, record
    else:
        if coord > record:
            return 1, coord
        elif coord == record:
            return 0, record
        return -1, record


def get_coord_at_direction(node, direction, opposite=False):
    '''Returns the respective node coordinate at the given direction.'''
    if opposite:
        return node.position.y if direction in ('lsb', 'rsb') else node.position.x
    return node.position.x if direction in ('lsb', 'rsb') else node.position.y


def get_midpoint(node_start, node_end, direction):
    if direction in ('lsb', 'rsb'):
        return (node_start.position.y + node_end.position.y) / 2
    return (node_start.position.x + node_end.position.x) / 2


def get_outermost_strokes(layer, direction):
    direction = direction.lower()
    assert direction in ('lsb', 'rsb', 'tsb', 'bsb')

    # Idea: all adjacent outermost point counts as one stroke
    record = None
    outermost_points = []
    stroke_start = None
    stroke_end = None
    for path in layer.paths:
        for node in path.nodes:
            if node.type == 'offcurve':
                # Skip handle nodes
                # IMPORTANT: This assumes that outermost pixels are determined by nodes, rather than curves, which is also best practice
                continue
            comparison, new_record = compare_node_to_record(node, record, direction)
            if comparison == -1: # Does not break record
                if stroke_end is not None: # Record breaking stroke has ended
                    outermost_points.append(get_midpoint(stroke_start, stroke_end, direction))
                    stroke_start = None
                    stroke_end = None
            elif comparison == 1: # Breaks outermost record
                record = new_record
                outermost_points = []
                stroke_start = node
                stroke_end = node
            else: # Same with current record
                if stroke_start is None: # Another stroke with the same record
                    stroke_start = node
                stroke_end = node # Otherwise, currently on a record breaking stroke, still have to update end node
        if stroke_end is not None: # When outermost stroke ends with path (either individual stroke or one that extends into the initial nodes)
            if path.closed and compare_node_to_record(path.nodes[0], record, direction)[0] == 0: # Check if the last stroke continues to the intial stroke (hence double counted)
                del outermost_points[0] # Remove the incomplete initial stroke
                for node in path.nodes: # Extend this stroke to the farthest initial node
                    if node == stroke_start:
                        break
                    comparison, _ = compare_node_to_record(node, record, direction)
                    if comparison == 0:
                        stroke_end = node
                    elif comparison == -1:
                        break
            outermost_points.append(get_midpoint(stroke_start, stroke_end, direction))
            stroke_start = None
            stroke_end = None

    return outermost_points, record


@lru_cache
def get_outermost_range(layer, direction):
    direction = direction.lower()
    assert direction in ('lsb', 'rsb', 'tsb', 'bsb')

    record = None
    outermost_range = [-1, None]
    for path in layer.paths:
        # Possible optimization: check bound of each path to see if it lies within record
        for node in path.nodes:
            if node.type == 'offcurve':
                # Skip handle nodes
                # IMPORTANT: This assumes that outermost pixels are determined by nodes, rather than curves, which is also best practice
                continue
            comparison, new_record = compare_node_to_record(node, record, direction)
            if comparison == -1: # Does not break record
                continue
            elif comparison == 1: # Breaks outermost record
                record = new_record
                coord = get_coord_at_direction(node, direction, opposite=True)
                outermost_range = [coord, coord]
            else: # Same with current record
                coord = get_coord_at_direction(node, direction, opposite=True)
                if None in outermost_range: # First time updating
                    outermost_range = [coord, coord]
                elif coord < outermost_range[0]:
                    outermost_range[0] = coord
                elif coord > outermost_range[1]:
                    outermost_range[1] = coord
    return outermost_range, record


def layer_to_svg(layer: GSLayer, scaling: float = 1.0, inverted: bool = False) -> str:
    '''
    Convert a glyph layer to SVG format code string.
    If `inverted` is True, the SVG will be a white glyph on black background.
    '''
    width = layer.width
    ascender = layer.master.ascender
    descender = -layer.master.descender
    height = ascender + descender # Does this work for Chinese glyphs?
    assert height == layer.vertWidth #?

    path_code = ''
    for path in layer.shapes:
        if isinstance(path, GSComponent):
            raise NotImplementedError('Components are not supported yet.')
        elif not isinstance(path, GSPath):
            raise ValueError(f'Unexpected shape {path}.')

        # Note for SVG, origin is at top-left rather than bottom-left
        path_code += 'M {} {} '.format(
            path.nodes[-1].position.x * scaling,
            (ascender - path.nodes[-1].position.y) * scaling
        )
        i = 0
        while i < len(path.nodes):
            node = path.nodes[i]
            if node.type == OFFCURVE:
                assert node.nextNode.type == OFFCURVE
                assert node.nextNode.nextNode.type == CURVE
                path_code += 'C {} {}, {} {}, {} {} '.format(
                    node.position.x * scaling,
                    (ascender - node.position.y) * scaling,
                    node.nextNode.position.x * scaling,
                    (ascender - node.nextNode.position.y) * scaling,
                    node.nextNode.nextNode.position.x * scaling,
                    (ascender - node.nextNode.nextNode.position.y) * scaling
                )
                i += 2
            elif node.type == LINE:
                path_code += 'L {} {} '.format(
                    node.position.x * scaling,
                    (ascender - node.position.y) * scaling
                )
            elif node.type == CURVE:
                # All curve nodes should be handled in the OFFCURVE case
                raise ValueError(f'Unexpected occurrence of curve node {node}.')
            elif node.type == QCURVE:
                raise NotImplementedError('Quadratic curves are not supported yet.')
            i += 1
        path_code += 'Z' # What about open curves?
    svg_code = f'<svg width="{width * scaling}" height="{height * scaling}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="{'black' if inverted else 'white'}"/><path d="{path_code}" fill="{'white' if inverted else 'black'}"/></svg>'
    return svg_code


def layer_to_numpy(layer: GSLayer, scaling: float = 1.0, inverted: bool = False, method: str = 'pyvips') -> np.array:
    '''
    Rasterize a glyph layer into a grayscale numpy array.
    '''
    assert method in ('cairo', 'aggdraw', 'pyvips')
    svg_bytes = layer_to_svg(layer, scaling, inverted).encode()
    if method == 'pyvips':
        import pyvips
        im = pyvips.Image.svgload_buffer(svg_bytes) # dpi, scale
        return im.numpy()[:, :, 0]
    elif method == 'cairo':
        import io
        import cairosvg
        from PIL import Image
        png_bytes = cairosvg.svg2png(svg_bytes)
        im = Image.open(io.BytesIO(png_bytes)).convert('L')
        return np.asarray(im)
    elif method == 'aggdraw':
        raise NotImplementedError('The aggdraw method is not supported yet.')
