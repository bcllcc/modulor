"""Low-level geometry helpers: vectors, transforms, arcs, polylines, wall outlines.

All angles in the public op API are degrees, CCW, measured from +X.
2D points are [x, y]; 3D points are [x, y, z]. Z is up.
"""
from __future__ import annotations

import math

import numpy as np

TAU = math.tau

# ---------------------------------------------------------------- units

MM_PER_UNIT = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}


def unit_scale(units: str) -> float:
    """Millimetres per document unit."""
    return MM_PER_UNIT[units]


# ---------------------------------------------------------------- vec2

def v2(p) -> np.ndarray:
    a = np.asarray(p, dtype=float)
    if a.shape != (2,):
        raise ValueError(f"expected 2D point [x, y], got {p!r}")
    return a


def v3(p) -> np.ndarray:
    a = np.asarray(p, dtype=float).ravel()
    if a.shape == (2,):
        a = np.array([a[0], a[1], 0.0])
    if a.shape != (3,):
        raise ValueError(f"expected 3D point [x, y, z], got {p!r}")
    return a


def norm(v) -> float:
    return float(np.linalg.norm(v))


def unit(v) -> np.ndarray:
    n = norm(v)
    if n < 1e-12:
        raise ValueError("zero-length vector")
    return np.asarray(v, dtype=float) / n


def perp(v) -> np.ndarray:
    """CCW perpendicular of a 2D vector."""
    return np.array([-v[1], v[0]], dtype=float)


# ---------------------------------------------------------------- 2D affine (3x3)

def mat2_identity() -> np.ndarray:
    return np.eye(3)


def mat2_translate(dx: float, dy: float) -> np.ndarray:
    m = np.eye(3)
    m[0, 2], m[1, 2] = dx, dy
    return m


def mat2_rotate(deg: float, center=(0.0, 0.0)) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    cx, cy = center
    m = np.array([[c, -s, cx - c * cx + s * cy],
                  [s, c, cy - s * cx - c * cy],
                  [0, 0, 1.0]])
    return m


def mat2_scale(fx: float, fy: float, center=(0.0, 0.0)) -> np.ndarray:
    cx, cy = center
    return np.array([[fx, 0, cx - fx * cx],
                     [0, fy, cy - fy * cy],
                     [0, 0, 1.0]])


def mat2_mirror(p1, p2) -> np.ndarray:
    """Reflection across the line through p1-p2."""
    p1 = v2(p1)
    d = unit(v2(p2) - p1)
    c, s = d[0], d[1]
    # reflect about line through origin with direction d, conjugated by translation
    r = np.array([[c * c - s * s, 2 * c * s, 0],
                  [2 * c * s, s * s - c * c, 0],
                  [0, 0, 1.0]])
    t1 = mat2_translate(-p1[0], -p1[1])
    t2 = mat2_translate(p1[0], p1[1])
    return t2 @ r @ t1


def apply2(m: np.ndarray, p) -> list[float]:
    p = v2(p)
    q = m @ np.array([p[0], p[1], 1.0])
    return [float(q[0]), float(q[1])]


def apply2_many(m: np.ndarray, pts) -> list[list[float]]:
    return [apply2(m, p) for p in pts]


def mat2_is_uniform(m: np.ndarray) -> bool:
    """True if the linear part is a uniform scale + rotation (+ mirror)."""
    a = m[:2, :2]
    sx = norm(a[:, 0])
    sy = norm(a[:, 1])
    ortho = abs(float(a[:, 0] @ a[:, 1])) < 1e-9 * max(sx * sy, 1e-12)
    return ortho and abs(sx - sy) < 1e-9 * max(sx, 1e-12)


def mat2_uniform_factor(m: np.ndarray) -> float:
    return norm(m[:2, 0])


def mat2_angle(m: np.ndarray) -> float:
    """Rotation (deg) carried by the linear part (assumes uniform)."""
    return math.degrees(math.atan2(m[1, 0], m[0, 0]))


def mat2_flips(m: np.ndarray) -> bool:
    return float(np.linalg.det(m[:2, :2])) < 0


# ---------------------------------------------------------------- 3D affine (4x4)

def mat3_identity() -> np.ndarray:
    return np.eye(4)


def mat3_translate(dx, dy, dz) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = [dx, dy, dz]
    return m


def mat3_scale(fx, fy, fz, center=(0, 0, 0)) -> np.ndarray:
    c = v3(center)
    m = np.eye(4)
    m[0, 0], m[1, 1], m[2, 2] = fx, fy, fz
    m[:3, 3] = c - np.array([fx, fy, fz]) * c
    return m


def mat3_rotate_axis(axis, deg: float, point=(0, 0, 0)) -> np.ndarray:
    """Rotation about an arbitrary axis direction through `point`."""
    u = unit(v3(axis))
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = u
    r = np.array([
        [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
        [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
        [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
    ])
    p = v3(point)
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = p - r @ p
    return m


def mat3_mirror_plane(p1, p2) -> np.ndarray:
    """Reflection across the vertical plane through 2D line p1-p2."""
    m2 = mat2_mirror(p1, p2)
    m = np.eye(4)
    m[:2, :2] = m2[:2, :2]
    m[:2, 3] = m2[:2, 2]
    return m


def mat3_from_mat2(m2: np.ndarray) -> np.ndarray:
    m = np.eye(4)
    m[:2, :2] = m2[:2, :2]
    m[:2, 3] = m2[:2, 2]
    return m


def mat3_to_manifold(m: np.ndarray) -> np.ndarray:
    """manifold3d wants a 3x4 row-major affine."""
    return np.ascontiguousarray(m[:3, :4], dtype=float)


# ---------------------------------------------------------------- arcs / circles

def arc_points(center, radius: float, start_deg: float, end_deg: float,
               segments: int = 0) -> list[list[float]]:
    """Discretize a CCW arc. end < start is normalized by +360."""
    cx, cy = v2(center)
    sweep = (end_deg - start_deg) % 360.0
    if sweep == 0.0:
        sweep = 360.0
    if segments <= 0:
        segments = max(8, int(math.ceil(sweep / 360.0 * default_circle_segments(radius))))
    pts = []
    for i in range(segments + 1):
        a = math.radians(start_deg + sweep * i / segments)
        pts.append([cx + radius * math.cos(a), cy + radius * math.sin(a)])
    return pts


def circle_points(center, radius: float, segments: int = 0) -> list[list[float]]:
    if segments <= 0:
        segments = default_circle_segments(radius)
    pts = arc_points(center, radius, 0.0, 360.0, segments)
    return pts[:-1]  # closed implicitly


def default_circle_segments(radius: float) -> int:
    # quality scales gently with radius; clamped to a sane band
    return int(min(128, max(16, round(math.sqrt(max(radius, 0.01)) * 12))))


# ---------------------------------------------------------------- polylines

def polyline_length(pts, closed: bool = False) -> float:
    p = np.asarray(pts, dtype=float)
    if len(p) < 2:
        return 0.0
    segs = np.diff(p, axis=0)
    total = float(np.sqrt((segs ** 2).sum(axis=1)).sum())
    if closed:
        total += norm(p[0] - p[-1])
    return total


def polygon_area(pts) -> float:
    """Signed area (CCW positive)."""
    p = np.asarray(pts, dtype=float)
    if len(p) < 3:
        return 0.0
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def point_along_path(pts, dist: float):
    """Point + unit direction at arc-length `dist` along an open polyline.

    Returns (point ndarray, direction ndarray, segment_index)."""
    p = [v2(q) for q in pts]
    if len(p) < 2:
        raise ValueError("path needs at least 2 points")
    remaining = dist
    for i in range(len(p) - 1):
        seg = p[i + 1] - p[i]
        L = norm(seg)
        if L < 1e-12:
            continue
        if remaining <= L or i == len(p) - 2:
            d = unit(seg)
            return p[i] + d * min(remaining, L), d, i
        remaining -= L
    d = unit(p[-1] - p[-2])
    return p[-1], d, len(p) - 2


def offset_polyline(pts, delta: float, miter_limit: float = 4.0) -> list[list[float]]:
    """Offset an open polyline to one side (positive = left of travel).

    Miter joins, clamped to `miter_limit * |delta|`. Returns the offset point list.
    """
    p = [v2(q) for q in pts]
    # drop duplicate consecutive points
    clean = [p[0]]
    for q in p[1:]:
        if norm(q - clean[-1]) > 1e-9:
            clean.append(q)
    p = clean
    if len(p) < 2:
        raise ValueError("polyline needs at least 2 distinct points")
    dirs = [unit(p[i + 1] - p[i]) for i in range(len(p) - 1)]
    out = [p[0] + perp(dirs[0]) * delta]
    for i in range(1, len(p) - 1):
        d0, d1 = dirs[i - 1], dirs[i]
        n0, n1 = perp(d0), perp(d1)
        bis = n0 + n1
        bl = norm(bis)
        if bl < 1e-9:  # 180-degree turn: square it off
            out.append(p[i] + n0 * delta)
            out.append(p[i] + n1 * delta)
            continue
        bis = bis / bl
        denom = float(bis @ n0)
        L = delta / denom if abs(denom) > 1e-9 else delta * miter_limit
        if abs(L) > abs(delta) * miter_limit:  # clamp long spikes -> bevel
            out.append(p[i] + n0 * delta)
            out.append(p[i] + n1 * delta)
        else:
            out.append(p[i] + bis * L)
    out.append(p[-1] + perp(dirs[-1]) * delta)
    return [[float(x), float(y)] for x, y in out]


def offset_ring(pts, delta: float, miter_limit: float = 4.0) -> list[list[float]]:
    """Offset a closed ring (no duplicate end point) with cyclic miter joins."""
    p = [v2(q) for q in pts]
    clean = []
    for q in p:
        if not clean or norm(q - clean[-1]) > 1e-9:
            clean.append(q)
    if len(clean) > 1 and norm(clean[0] - clean[-1]) < 1e-9:
        clean.pop()
    p = clean
    if len(p) < 3:
        raise ValueError("ring needs at least 3 distinct points")
    n = len(p)
    dirs = [unit(p[(i + 1) % n] - p[i]) for i in range(n)]
    out = []
    for i in range(n):
        d0, d1 = dirs[(i - 1) % n], dirs[i]
        n0, n1 = perp(d0), perp(d1)
        bis = n0 + n1
        bl = norm(bis)
        if bl < 1e-9:
            out.append(p[i] + n0 * delta)
            out.append(p[i] + n1 * delta)
            continue
        bis = bis / bl
        denom = float(bis @ n0)
        L = delta / denom if abs(denom) > 1e-9 else delta * miter_limit
        if abs(L) > abs(delta) * miter_limit:
            out.append(p[i] + n0 * delta)
            out.append(p[i] + n1 * delta)
        else:
            out.append(p[i] + bis * L)
    return [[float(x), float(y)] for x, y in out]


def path_is_closed(path) -> bool:
    return len(path) > 3 and norm(v2(path[0]) - v2(path[-1])) < 1e-9


def wall_outline(path, thickness: float) -> list[list[list[float]]]:
    """Footprint contour(s) of a wall drawn along its centerline.

    Open path -> one closed polygon (square caps, miter joins).
    Closed path (first point repeated last) -> ring: outer contour CCW plus
    inner contour CW (a hole), so courtyards/rooms stay open.
    """
    half = thickness / 2.0
    if path_is_closed(path):
        ring = path[:-1]
        a = offset_ring(ring, +half)
        b = offset_ring(ring, -half)
        if abs(polygon_area(a)) < abs(polygon_area(b)):
            a, b = b, a
        return [ensure_ccw(a), ensure_ccw(b)[::-1]]
    left = offset_polyline(path, +half)
    right = offset_polyline(path, -half)
    return [ensure_ccw(left + right[::-1])]


def ensure_ccw(pts) -> list[list[float]]:
    """Force CCW orientation (positive area), as required by Positive fill."""
    pts = [[float(p[0]), float(p[1])] for p in pts]
    return pts if polygon_area(pts) >= 0 else pts[::-1]


# ---------------------------------------------------------------- corner rounding

def round_corners(pts, closed: bool, radius: float, chamfer: bool = False,
                  segments: int = 0) -> tuple[list[list[float]], int, int]:
    """Fillet (arc) or chamfer (cut) the corners of a polyline.

    Radius is clamped per-corner when the adjacent segments are too short.
    Returns (new_points, corners_done, corners_clamped).
    """
    p = [v2(q) for q in pts]
    n = len(p)
    if n < 3:
        return [[float(a), float(b)] for a, b in p], 0, 0
    out: list[list[float]] = []
    done = clamped = 0
    rng = range(n) if closed else range(1, n - 1)
    corner_set = set(rng)
    for i in range(n):
        if i not in corner_set:
            out.append([float(p[i][0]), float(p[i][1])])
            continue
        prev_pt = p[(i - 1) % n]
        next_pt = p[(i + 1) % n]
        v0 = p[i] - prev_pt
        v1 = next_pt - p[i]
        l0, l1 = norm(v0), norm(v1)
        if l0 < 1e-9 or l1 < 1e-9:
            out.append([float(p[i][0]), float(p[i][1])])
            continue
        d0, d1 = v0 / l0, v1 / l1
        cosq = max(-1.0, min(1.0, float(d0 @ d1)))
        theta = math.acos(cosq)  # turn angle
        if theta < math.radians(2) or theta > math.radians(178):
            out.append([float(p[i][0]), float(p[i][1])])
            continue
        t = radius if chamfer else radius * math.tan(theta / 2)
        t_max = 0.5 * min(l0, l1)
        if t > t_max:
            t = t_max
            clamped += 1
        start = p[i] - d0 * t
        end = p[i] + d1 * t
        if chamfer:
            out.append([float(start[0]), float(start[1])])
            out.append([float(end[0]), float(end[1])])
        else:
            r_eff = t / math.tan(theta / 2)
            cross = float(d0[0] * d1[1] - d0[1] * d1[0])
            side = 1.0 if cross > 0 else -1.0
            center = start + perp(d0) * side * r_eff
            a0 = math.atan2(start[1] - center[1], start[0] - center[0])
            a1 = math.atan2(end[1] - center[1], end[0] - center[0])
            sweep = (a1 - a0)
            while sweep * side < 0:
                sweep += side * TAU
            segs = segments or max(2, int(abs(sweep) / math.radians(12)))
            for k in range(segs + 1):
                a = a0 + sweep * k / segs
                out.append([float(center[0] + r_eff * math.cos(a)),
                            float(center[1] + r_eff * math.sin(a))])
        done += 1
    return out, done, clamped


# ---------------------------------------------------------------- splines

def catmull_rom(pts, closed: bool = False, samples_per_seg: int = 12,
                alpha: float = 0.5) -> list[list[float]]:
    """Centripetal Catmull-Rom spline through the given points (2D or 3D).

    Returns a dense polyline. Open splines start/end exactly at the first
    and last points; closed splines wrap smoothly (no duplicate end point).
    """
    p = [np.asarray(q, dtype=float) for q in pts]
    clean = []
    for q in p:
        if not clean or norm(q - clean[-1]) > 1e-9:
            clean.append(q)
    if closed and len(clean) > 1 and norm(clean[0] - clean[-1]) < 1e-9:
        clean.pop()
    p = clean
    if len(p) < 3:
        return [[float(v) for v in q] for q in p]
    n = len(p)
    segs = n if closed else n - 1
    out = []
    for i in range(segs):
        if closed:
            p0, p1, p2, p3 = p[(i - 1) % n], p[i], p[(i + 1) % n], p[(i + 2) % n]
        else:
            p1, p2 = p[i], p[i + 1]
            p0 = p[i - 1] if i > 0 else 2 * p1 - p2          # mirror phantom
            p3 = p[i + 2] if i + 2 < n else 2 * p2 - p1
        t0 = 0.0
        t1 = t0 + max(norm(p1 - p0) ** alpha, 1e-9)
        t2 = t1 + max(norm(p2 - p1) ** alpha, 1e-9)
        t3 = t2 + max(norm(p3 - p2) ** alpha, 1e-9)
        for j in range(samples_per_seg):
            t = t1 + (t2 - t1) * j / samples_per_seg
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            c = (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2
            out.append([float(v) for v in c])
    if not closed:
        out.append([float(v) for v in p[-1]])
    return out


def resample_closed(pts, n: int) -> np.ndarray:
    """Resample a closed 2D contour to exactly n points, uniform by arc length."""
    p = np.asarray(pts, dtype=float)
    if norm(p[0] - p[-1]) < 1e-9:
        p = p[:-1]
    ring = np.vstack([p, p[:1]])
    seg = np.linalg.norm(np.diff(ring, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total < 1e-12:
        raise ValueError("contour has zero length")
    ts = np.linspace(0.0, total, n, endpoint=False)
    idx = np.searchsorted(cum, ts, side="right") - 1
    idx = np.clip(idx, 0, len(seg) - 1)
    frac = (ts - cum[idx]) / np.maximum(seg[idx], 1e-12)
    return ring[idx] + (ring[idx + 1] - ring[idx]) * frac[:, None]


# ---------------------------------------------------------------- bbox

class BBox:
    def __init__(self):
        self.min = None
        self.max = None

    def add(self, pt):
        p = np.asarray(pt, dtype=float)
        if p.shape == (2,):
            p = np.array([p[0], p[1], 0.0])
        if self.min is None:
            self.min = p.copy()
            self.max = p.copy()
        else:
            self.min = np.minimum(self.min, p)
            self.max = np.maximum(self.max, p)

    def add_many(self, pts):
        for p in pts:
            self.add(p)

    def merge(self, other: "BBox"):
        if other.min is not None:
            self.add(other.min)
            self.add(other.max)

    @property
    def empty(self) -> bool:
        return self.min is None

    def as_dict(self):
        if self.empty:
            return None
        return {"min": [round(float(v), 6) for v in self.min],
                "max": [round(float(v), 6) for v in self.max]}

    def size(self):
        if self.empty:
            return np.zeros(3)
        return self.max - self.min

    def center(self):
        if self.empty:
            return np.zeros(3)
        return (self.max + self.min) / 2.0


def fmt_num(x: float, max_decimals: int = 2) -> str:
    """CAD-style number formatting: trim trailing zeros after the point."""
    s = f"{x:.{max_decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-", "-0") else "0"
