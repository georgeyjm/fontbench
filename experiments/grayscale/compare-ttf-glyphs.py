from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen


# def glyph_to_svg(glyph, output_path=None):
#     # Get glyph metrics
#     pen = SVGPathPen(glyph_set)
#     glyph.draw(pen)
    
#     # Get bounds for viewBox
#     bounds_pen = BoundsPen(glyph_set)
#     glyph.draw(bounds_pen)
#     bounds = bounds_pen.bounds  # (xMin, yMin, xMax, yMax)
    
#     if bounds:
#         xMin, yMin, xMax, yMax = bounds
#         width = xMax - xMin
#         height = yMax - yMin
        
#         # SVG coordinate system is Y-down, fonts are Y-up
#         svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{xMin} {-yMax} {width} {height}"><g transform="scale(1,-1)"><path d="{pen.getCommands()}" fill="black"/></g></svg>'
#     else:
#         svg = None  # Empty glyph (like space)
    
#     if output_path:
#         with open(output_path, 'w') as f:
#             f.write(svg)
    
#     return svg




def glyph_to_svg(font: TTFont, glyph: str, output_path: str = None) -> str:
    cmap = font.getBestCmap()
    glyph_id = cmap.get(glyph)
    if glyph_id is None:
        raise ValueError(f'Glyph "{glyph}" not found in font.')
    
    glyph = font.getGlyphSet()[glyph_id]
    width = glyph.width
    
    # Get vertical metrics from OS/2 or hhea table
    if 'OS/2' in font:
        ascender = font['OS/2'].sTypoAscender
        descender = font['OS/2'].sTypoDescender
    else:
        ascender = font['hhea'].ascent
        descender = font['hhea'].descent
    height = ascender - descender
    
    # Draw the glyph
    pen = SVGPathPen(glyph_set)
    glyph.draw(pen)
    path_data = pen.getCommands()
    
    # viewBox: x=0, y=-ascender (because we flip Y), width, height
    svg_code = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 {-ascender} {width} {height}"><g transform="scale(1,-1)"><path d="{path_data}" fill="black"/></g></svg>'
    
    if output_path:
        with open(output_path, 'w') as f:
            f.write(svg_code)
    
    return svg_code


# Load the font
font = TTFont('各种黑体大全/OPPO Sans 4.0.ttf')

# Get the glyph set
glyph_set = font.getGlyphSet()

# Get a specific glyph and convert to SVG path
glyph_name = "A"  # or use font.getGlyphOrder() to list all glyphs
pen = SVGPathPen(glyph_set)
glyph_set[glyph_name].draw(pen)

# Get the SVG path data (the "d" attribute)
svg_path_data = pen.getCommands()
print(svg_path_data)  # e.g., "M 100 0 L 200 700 L 300 0 Z"
