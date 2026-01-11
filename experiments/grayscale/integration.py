import re
from typing import Iterable, Tuple, List, Union


Point = Tuple[float, float]
Seg   = Tuple[str, Tuple[float, ...]]  # ('L',(x1,y1)), ('Q',(cx,x2,y2)), ('C',(cx1,cy1,cx2,cy2,x2,y2))
Path  = List[Union[Tuple[str, float, float], Seg, Tuple[str]]]  # starts with ('M',x0,y0); may end with ('Z',)


def line_xy(p0: Point, p1: Point):
    dx, dy = p1[0]-p0[0], p1[1]-p0[1]
    def xy(t):  return (p0[0] + t*dx, p0[1] + t*dy)
    def dxy(t): return (dx, dy)
    return xy, dxy

def quad_xy(p0: Point, c: Point, p1: Point):
    # B(t) = (1-t)^2 p0 + 2(1-t)t c + t^2 p1
    def xy(t):
        u = 1.0 - t
        return (u*u*p0[0] + 2*u*t*c[0] + t*t*p1[0],
                u*u*p0[1] + 2*u*t*c[1] + t*t*p1[1])
    def dxy(t):
        # B'(t) = 2((1-t)(c - p0) + t(p1 - c))
        u = 1.0 - t
        dx = 2.0*(u*(c[0]-p0[0]) + t*(p1[0]-c[0]))
        dy = 2.0*(u*(c[1]-p0[1]) + t*(p1[1]-c[1]))
        return dx, dy
    return xy, dxy

def cubic_xy(p0: Point, c1: Point, c2: Point, p1: Point):
    # B(t) = Σ Bernstein * control
    def xy(t):
        u = 1.0 - t
        u2, t2 = u*u, t*t
        b0 = u2*u
        b1 = 3*u2*t
        b2 = 3*u*t2
        b3 = t2*t
        return (b0*p0[0] + b1*c1[0] + b2*c2[0] + b3*p1[0],
                b0*p0[1] + b1*c1[1] + b2*c2[1] + b3*p1[1])
    def dxy(t):
        u = 1.0 - t
        # B'(t) = 3[(c1-p0)u^2 + 2(c2-c1)ut + (p1-c2)t^2]
        dx = 3*((c1[0]-p0[0])*u*u + 2*(c2[0]-c1[0])*u*t + (p1[0]-c2[0])*t*t)
        dy = 3*((c1[1]-p0[1])*u*u + 2*(c2[1]-c1[1])*u*t + (p1[1]-c2[1])*t*t)
        return dx, dy
    return xy, dxy

# --- Numeric integral per segment (Simpson) -----------------------------------

def simpson_integral(f, n=200):
    # n must be even
    if n % 2: n += 1
    h = 1.0 / n
    s = f(0.0) + f(1.0)
    odd = 0.0
    even = 0.0
    for k in range(1, n):
        t = k * h
        if k % 2:
            odd += f(t)
        else:
            even += f(t)
    return (s + 4*odd + 2*even) * h / 3.0

def oriented_area_of_segment(xy_func, dxy_func, n=200):
    def integrand(t):
        x, y = xy_func(t)
        dx, dy = dxy_func(t)
        return x*dy - y*dx
    return 0.5 * simpson_integral(integrand, n)

# --- Path parsing & area -------------------------------------------------------

def area_of_paths(paths: Iterable[Path], samples_per_segment: int = 200) -> float:
    """
    Compute signed area using non-zero winding rule:
    outer contours should be CCW (+ area), holes CW (- area).
    """
    total = 0.0
    for path in paths:
        assert path and path[0][0] == 'M', "Each path must start with ('M', x, y)"
        x0, y0 = path[0][1], path[0][2]
        curr = (x0, y0)
        i = 1
        while i < len(path):
            op = path[i][0]
            if op == 'L':
                x1, y1 = path[i][1]
                xy, dxy = line_xy(curr, (x1, y1))
                total += oriented_area_of_segment(xy, dxy, samples_per_segment)
                curr = (x1, y1)
            elif op == 'Q':
                cx, cy, x1, y1 = path[i][1]
                xy, dxy = quad_xy(curr, (cx, cy), (x1, y1))
                total += oriented_area_of_segment(xy, dxy, samples_per_segment)
                curr = (x1, y1)
            elif op == 'C':
                cx1, cy1, cx2, cy2, x1, y1 = path[i][1]
                xy, dxy = cubic_xy(curr, (cx1, cy1), (cx2, cy2), (x1, y1))
                total += oriented_area_of_segment(xy, dxy, samples_per_segment)
                curr = (x1, y1)
            elif op == 'Z':
                # Close with a line if not already closed
                if curr != (x0, y0):
                    xy, dxy = line_xy(curr, (x0, y0))
                    total += oriented_area_of_segment(xy, dxy, samples_per_segment)
                # end this subpath
                curr = (x0, y0)
            else:
                raise ValueError(f"Unknown segment type: {op}")
            i += 1
    return total  # signed


def occupancy_ratio(paths: Iterable[Path], width_px: int, height_px: int, samples_per_segment: int = 200) -> float:
    area = abs(area_of_paths(paths, samples_per_segment))
    return area / (width_px * height_px)


def svg_to_paths(svg_code: str) -> Iterable[Path]:
    """
    Parse a minimal SVG path "d" string into a list of Path objects.
    Supports 'M', 'L', 'Q', 'C', 'Z' commands as used in sample texts.
    Only supports absolute coordinates.
    """
    # Pattern: Match commands and groups of floats, allow for commas and whitespace separators
    cmd_re = re.compile(r'([MLQCZ])|(-?\d*\.?\d+)')
    
    tokens = []
    for m in cmd_re.finditer(svg_code):
        if m.group(1):
            tokens.append(m.group(1))
        else:
            tokens.append(float(m.group(2)))

    paths = []
    i = 0
    n = len(tokens)
    curr_path = []
    while i < n:
        t = tokens[i]
        if t == 'M':
            if curr_path:
                paths.append(curr_path)
                curr_path = []
            x = tokens[i+1]
            y = tokens[i+2]
            curr_path.append(('M', x, y))
            i += 3
        elif t == 'L':
            x = tokens[i+1]
            y = tokens[i+2]
            curr_path.append(('L', (x, y)))
            i += 3
        elif t == 'C':
            # C cx1 cy1, cx2 cy2, x y   -- 6 numbers
            cx1 = tokens[i+1]
            cy1 = tokens[i+2]
            cx2 = tokens[i+3]
            cy2 = tokens[i+4]
            x   = tokens[i+5]
            y   = tokens[i+6]
            curr_path.append(('C', (cx1, cy1, cx2, cy2, x, y)))
            i += 7
        elif t == 'Q':
            # Q cx cy, x y  -- 4 numbers
            cx = tokens[i+1]
            cy = tokens[i+2]
            x  = tokens[i+3]
            y  = tokens[i+4]
            curr_path.append(('Q', (cx, cy, x, y)))
            i += 5
        elif t == 'Z':
            curr_path.append(('Z',))
            i += 1
        else:
            raise ValueError(f"Unexpected token in path: {t}")
    if curr_path:
        paths.append(curr_path)
    return paths
