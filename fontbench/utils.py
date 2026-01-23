from functools import lru_cache

import numpy as np
from glyphsLib import GSFont, GSGlyph, GSLayer, GSPath, GSComponent
from glyphsLib import LINE, CURVE, QCURVE, OFFCURVE
from glyphsLib.types import Transform


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
    if height != layer.vertWidth and layer.vertWidth is not None:
        print(f'Calculated height "{height}" ≠ vertWidth "{layer.vertWidth}" for layer "{layer.name}" of glyph "{layer.parent.id}" ("{layer.parent.string or layer.parent.unicode}")')
    if layer.vertWidth is not None:
        height = layer.vertWidth
    return height


def _path_to_svg_path_data(path: GSPath, ascender: float, scaling: float = 1.0) -> str:
    '''
    Convert a GSPath to SVG path data string.
    
    Arguments:
        path: The path to convert.
        ascender: The ascender value for coordinate transformation.
        scaling: The scaling factor to apply.
    '''
    # Make sure last node is not an offcurve node
    while path.nodes[-1].type == OFFCURVE:
        path.nodes.insert(0, path.nodes.pop(-1))

    # Note for SVG, origin is at top-left rather than bottom-left
    path_code = 'M {} {} '.format(
        path.nodes[-1].position.x * scaling,
        (ascender - path.nodes[-1].position.y) * scaling
    )
    
    i = 0
    while i < len(path.nodes):
        node = path.nodes[i]
        if node.type == OFFCURVE:
            if node.nextNode.type == OFFCURVE:
                if node.nextNode.nextNode.type == OFFCURVE:
                    # This is a rare edge case where quartic curves appear
                    # We simply don't handle this case for now
                    return ''
                assert node.nextNode.nextNode.type in (CURVE, QCURVE), f'Unexpected occurrence of {node.nextNode.nextNode.type} node {i+2} of {path} in {path.parent}.'
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
            elif node.nextNode.type == QCURVE:
                path_code += 'Q {} {}, {} {} '.format(
                    node.position.x * scaling,
                    (ascender - node.position.y) * scaling,
                    node.nextNode.position.x * scaling,
                    (ascender - node.nextNode.position.y) * scaling,
                )
                i += 2
                continue
            else:
                raise ValueError(f'Unexpected occurrence of node {i+1} of {path} in {path.parent}.')
        elif node.type == LINE:
            path_code += 'L {} {} '.format(
                node.position.x * scaling,
                (ascender - node.position.y) * scaling
            )
            i += 1
        elif node.type in (CURVE, QCURVE):
            # All curve nodes should be handled in the OFFCURVE case
            raise ValueError(f'Unexpected occurrence of curve/qcurve node {node}.')
    path_code += 'Z' # What about open curves?
    return path_code


def _component_to_svg_content(component: GSComponent, ascender: float, scaling: float = 1.0) -> str:
    '''
    Convert a GSComponent to SVG content string.
    This function is able to handle nested transformations through recursion.
    
    Arguments:
        component: The component to convert.
        ascender: The ascender value for coordinate transformation.
        scaling: The scaling factor to apply.
    
    Returns:
        SVG path data string with transformations applied via a <g> element.
    '''
    # Recursively convert the referenced layer to SVG content
    referenced_layer = component.layer if hasattr(component, 'layer') else getattr(component, 'componentLayer', None)
    if referenced_layer is None:
        raise ValueError(f'Component "{component.name}" has no corresponding layer.')
    component_svg_content = _layer_to_svg_content(referenced_layer, ascender, scaling)

    ### Handle transformations

    # Transform matrix (overrides individual transforms)
    if hasattr(component, 'transform') and (transform := component.transform) is not None:
        # SVG uses 2x3 matrices: matrix(a, b, c, d, e, f)
        if isinstance(transform, Transform) or isinstance(transform, (list, tuple)):
            assert len(transform) == 6, f'Transform must be a 2x3 matrix: {transform}'
            *matrix, x, y = transform
            transforms = [f'matrix({', '.join(map(str, matrix))}, {x * scaling}, {(y) * scaling})']
        elif hasattr(transform, 'transformStruct'):
            # Handle NSAffineTransform-like objects
            matrix = transform.transformStruct() if callable(transform.transformStruct) else transform.transformStruct
            *matrix, x, y = matrix
            if matrix and len(matrix) == 6:
                transforms = [f'matrix({', '.join(map(str, matrix))}, {x * scaling}, {(y) * scaling})']
    else:
        # Handle individual transforms
        transforms = []
        
        # Position (translate)
        position = getattr(component, 'position', None)
        if position is not None:
            x = position.x if hasattr(position, 'x') else position[0] if isinstance(position, (tuple, list)) else 0
            y = position.y if hasattr(position, 'y') else position[1] if isinstance(position, (tuple, list)) else 0
            # In SVG, y increases downward, so we need to flip the y coordinate
            transforms.append(f'translate({x * scaling}, {(ascender - y) * scaling})')
        
        # Scale
        scale = getattr(component, 'scale', None)
        if scale is not None:
            if isinstance(scale, (int, float)):
                scale_x = scale_y = scale
            elif hasattr(scale, 'x') and hasattr(scale, 'y'):
                scale_x, scale_y = scale.x, scale.y
            elif isinstance(scale, (tuple, list)) and len(scale) >= 2:
                scale_x, scale_y = scale[0], scale[1]
            else:
                scale_x = scale_y = 1.0
            if scale_x != 1.0 or scale_y != 1.0:
                transforms.append(f'scale({scale_x}, {scale_y})')
        
        # Rotation
        rotation = getattr(component, 'rotation', None)
        if rotation is not None:
            # Rotation is typically in degrees
            transforms.append(f'rotate({rotation})')
        
        # Slant (skewX)
        slant = getattr(component, 'slant', None)
        if slant is not None:
            # Slant is typically in degrees
            transforms.append(f'skewX({slant})')
    
    if transforms:
        # Wrap in a <g> element to apply potentially nested transformations
        return f'<g transform="{' '.join(transforms)}">{component_svg_content}</g>'
    return component_svg_content


def _layer_to_svg_content(layer: GSLayer, ascender: float, scaling: float = 1.0) -> tuple[str, bool]:
    '''
    Convert a glyph layer to SVG content string.
    This function handles both glyph layers and component layers, serving as an internal helper for recursion.
    
    Arguments:
        layer: The glyph layer to convert to SVG.
        ascender: The ascender value for coordinate transformation.
        scaling: The scaling factor to apply to the glyph layer.
    
    Returns:
        SVG content string of the layer.
    '''
    path_data_parts = []
    component_parts = []
    
    for shape in layer.shapes:
        if isinstance(shape, GSComponent):
            component_parts.append(_component_to_svg_content(shape, ascender, scaling))
        elif isinstance(shape, GSPath):
            path_data_parts.append(_path_to_svg_path_data(shape, ascender, scaling))
        else:
            raise ValueError(f'Unexpected shape: {shape}')

    combined_path_data = f'<path d="{' '.join(path_data_parts)}"/>'
    if not component_parts:
        return combined_path_data
    if path_data_parts:
        component_parts.insert(0, combined_path_data)
    return ''.join(component_parts)


def layer_to_svg(layer: GSLayer, scaling: float = 1.0, inverted: bool = False, full_svg: bool = True) -> str:
    '''    
    Convert a glyph layer to SVG format code string.

    Arguments:
        layer: The glyph layer to convert to SVG.
        scaling: The scaling factor to apply to the glyph layer.
        inverted: If True, the SVG will be a white glyph on black background.
        full_svg: Whether to include the full SVG document with a rectangle and a path.
    '''
    assert scaling > 0.0, 'Scaling factor must be positive.'
    width = layer.width
    ascender = layer.master.ascender
    height = get_layer_height(layer)

    svg_content = _layer_to_svg_content(layer, ascender, scaling)
    
    if not full_svg:
        # Return just the path data or SVG elements
        return svg_content
    
    # Build full SVG document with a wrapper for the fill color
    fill_color = 'white' if inverted else 'black'
    bg_color = 'black' if inverted else 'white'
    # Content contains SVG elements (<path> and/or <g>), wrap in a group
    svg_code = f'<svg width="{width * scaling}" height="{height * scaling}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="{bg_color}"/><g fill="{fill_color}">{svg_content}</g></svg>'
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
