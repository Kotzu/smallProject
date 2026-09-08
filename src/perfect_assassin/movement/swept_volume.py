"""Distance to triangle surfaces of a continuously translated upright capsule.

This is geometry, not a traversability certificate: supplied faces may be
partial, the start may be inside a solid, and actor dimensions/Z may be estimates.
No ray sampling, floor classification, input, or location-specific behavior.
"""
from dataclasses import dataclass
from math import isfinite, sqrt


def _sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _at(a, d, t):
    return tuple(x+t*y for x, y in zip(a, d))


def _point_segment2(p, a, b):
    d = _sub(b, a)
    length2 = _dot(d, d)
    t = 0 if length2 == 0 else max(0, min(1, _dot(_sub(p, a), d)/length2))
    delta = _sub(p, _at(a, d, t))
    return _dot(delta, delta)


def _segment_segment2(a, b, c, d):
    u, v, w = _sub(b, a), _sub(d, c), _sub(a, c)
    aa, bb, cc = _dot(u, u), _dot(u, v), _dot(v, v)
    dd, ee = _dot(u, w), _dot(v, w)
    best = min(_point_segment2(a, c, d), _point_segment2(b, c, d),
               _point_segment2(c, a, b), _point_segment2(d, a, b))
    determinant = aa*cc-bb*bb
    if determinant > 1e-14*aa*cc:
        s, t = (bb*ee-cc*dd)/determinant, (aa*ee-bb*dd)/determinant
        if 0 <= s <= 1 and 0 <= t <= 1:
            delta = _sub(_at(a, u, s), _at(c, v, t))
            best = min(best, _dot(delta, delta))
    return max(0, best)


def _inside_projection(p, triangle):
    a, b, c = triangle
    u, v, w = _sub(b, a), _sub(c, a), _sub(p, a)
    uu, uv, vv = _dot(u, u), _dot(u, v), _dot(v, v)
    wu, wv = _dot(w, u), _dot(w, v)
    determinant = uu*vv-uv*uv
    if determinant <= 1e-14*uu*vv:
        return False
    s, t = (vv*wu-uv*wv)/determinant, (uu*wv-uv*wu)/determinant
    return s >= -1e-12 and t >= -1e-12 and s+t <= 1+1e-12


def _edges(triangle):
    a, b, c = triangle
    return ((a, b), (b, c), (c, a))


def _point_triangle2(p, triangle):
    a, b, c = triangle
    normal = _cross(_sub(b, a), _sub(c, a))
    norm2 = _dot(normal, normal)
    if norm2 > 0 and _inside_projection(p, triangle):
        return _dot(_sub(p, a), normal)**2/norm2
    return min(_point_segment2(p, a, b) for a, b in _edges(triangle))


def _segment_triangle2(start, stop, triangle):
    a, b, c = triangle
    normal = _cross(_sub(b, a), _sub(c, a))
    direction = _sub(stop, start)
    denominator = _dot(direction, normal)
    if denominator != 0:
        t = _dot(_sub(a, start), normal)/denominator
        if 0 <= t <= 1 and _inside_projection(_at(start, direction, t), triangle):
            return 0.0
    return min(_point_triangle2(start, triangle), _point_triangle2(stop, triangle),
               *(_segment_segment2(start, stop, a, b) for a, b in _edges(triangle)))


def _triangle_triangle2(a, b):
    return min(*(_segment_triangle2(p, q, b) for p, q in _edges(a)),
               *(_segment_triangle2(p, q, a) for p, q in _edges(b)))


def _point(value):
    if len(value) != 3 or any(type(v) not in (int, float) or not isfinite(v) or abs(v)>100000 for v in value):
        raise ValueError("sweep point must be finite bounded XYZ")
    return tuple(float(v) for v in value)


@dataclass(frozen=True)
class SweptSurfaceDistance:
    minimum_separation_yards: float | None
    nearest_triangle_index: int | None
    triangle_count: int
    execution_authority: bool = False


def swept_capsule_surface_distance(start, stop, *, radius_yards, height_yards, triangles):
    """Exact linear sweep in supplied geometry, within floating-point tolerance.

    Capsule axis spans foot+radius to foot+height-radius. Its translation
    sweeps a parallelogram; the swept capsule is that surface dilated by a
    sphere. Distance is min triangle-to-parallelogram distance minus radius.
    Negative means surface overlap, NOT penetration depth. Floor/support
    contact is retained. Empty/partial geometry never becomes 'free space'.
    """
    start, stop = _point(start), _point(stop)
    if (type(radius_yards) not in (int, float) or not isfinite(radius_yards)
            or not 0.01 <= radius_yards <= 3
            or type(height_yards) not in (int, float) or not isfinite(height_yards)
            or not 2*radius_yards <= height_yards <= 10):
        raise ValueError("invalid explicit capsule dimensions")
    if _dot(_sub(stop, start), _sub(stop, start)) > 100**2:
        raise ValueError("sweep exceeds segment budget")
    if len(triangles) > 200000:
        raise ValueError("sweep exceeds triangle budget")
    def axial(p, height):
        return (p[0], p[1], p[2]+height)
    a, b = axial(start, radius_yards), axial(start, height_yards-radius_yards)
    c, d = axial(stop, height_yards-radius_yards), axial(stop, radius_yards)
    swept = ((a, b, c), (a, c, d))
    lower = tuple(min(p[i] for p in (a,b,c,d)) for i in range(3))
    upper = tuple(max(p[i] for p in (a,b,c,d)) for i in range(3))
    best, nearest = float('inf'), None
    for index, raw in enumerate(triangles):
        if len(raw) != 3:
            raise ValueError("surface must contain triangles")
        triangle = tuple(_point(p) for p in raw)
        # Exact distance lower bound, not sampling or an omitted-face budget.
        bound = sum(max(0, lower[i]-max(p[i] for p in triangle),
                        min(p[i] for p in triangle)-upper[i])**2 for i in range(3))
        if bound > best:
            continue
        value = min(_triangle_triangle2(part, triangle) for part in swept)
        if value < best:
            best, nearest = value, index
    return SweptSurfaceDistance(None if nearest is None else sqrt(best)-radius_yards,
                                nearest, len(triangles))
