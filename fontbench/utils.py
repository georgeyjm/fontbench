from functools import lru_cache

import numpy as np
from glyphsLib import GSFont, GSGlyph, GSLayer, GSPath, GSComponent
from glyphsLib import LINE, CURVE, QCURVE, OFFCURVE


@lru_cache
def get_glyph(font: GSFont, char: str) -> GSGlyph | None:
    '''
    DEPRECATED: Use font.glyphs[<target>] instead, which supports unicode, glyph string, and index
    Returns the glyph object given its glyph string or ID.
    '''
    return font.glyphs[char]

@lru_cache
def get_master_id_by_name(font: GSFont, master_name: str) -> str | None:
    '''
    Returns the master ID given its name.
    '''
    for master in font.masters:
        if master.name == master_name:
            return master.id

@lru_cache
def get_layer_by_master_name(glyph: GSGlyph, master_name: str) -> GSLayer | None:
    '''
    Returns the glyph's layer object given the name of that layer's master.
    '''
    master_id = get_master_id_by_name(glyph.parent, master_name)
    if master_id is None:
        return None
    return glyph.layers[master_id]

def get_layer_height(layer: GSLayer) -> float:
    '''
    Returns the height of a glyph layer.
    '''
    height = layer.master.ascender - layer.master.descender # Does this work for Chinese glyphs?
    # assert height == layer.vertWidth #?
    if height != layer.vertWidth:
        print(f'Calculated height "{height}" ≠ vertWidth "{layer.vertWidth}" for layer "{layer.name}" of glyph "{layer.parent.id}" ("{layer.parent.string or layer.parent.unicode}")')
    if layer.vertWidth is not None:
        height = layer.vertWidth
    return height


def layer_to_svg(layer: GSLayer, scaling: float = 1.0, inverted: bool = False, full_svg: bool = True) -> str:
    '''    
    Convert a glyph layer to SVG format code string.

    Arguments:
        layer: The glyph layer to convert to SVG.
        scaling: The scaling factor to apply to the glyph layer.
        inverted: If True, the SVG will be a white glyph on black background.
        full_svg: Whether to include the full SVG document with a rectangle and a path.
    '''
    assert 0.0 <= scaling <= 1.0, 'Scaling factor must be between 0 and 1.'
    width = layer.width
    ascender = layer.master.ascender
    height = get_layer_height(layer)

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
                i += 3
                continue
            elif node.type == LINE:
                path_code += 'L {} {} '.format(
                    node.position.x * scaling,
                    (ascender - node.position.y) * scaling
                )
                i += 1
            elif node.type == CURVE:
                # All curve nodes should be handled in the OFFCURVE case
                raise ValueError(f'Unexpected occurrence of curve node {node}.')
            elif node.type == QCURVE:
                raise NotImplementedError('Quadratic curves are not supported yet.')
        path_code += 'Z' # What about open curves?
    
    if not full_svg:
        return path_code
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
