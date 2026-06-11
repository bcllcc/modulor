"""Render solids/walls to a shaded PNG: z-buffer rasterizer, flat shading,
feature-edge overlay and an XYZ orientation gizmo. Built so a multimodal
agent can *look at* what it modeled.
"""
from __future__ import annotations

import math

import numpy as np

from .. import shapes
from ..errors import CadError
from . import font
from .raster import Canvas

# named orthographic views: (eye direction from target, up hint)
VIEWS = {
    "iso": ((1.0, -1.0, 0.75), (0, 0, 1)),
    "iso_left": ((-1.0, -1.0, 0.75), (0, 0, 1)),
    "iso_back": ((-1.0, 1.0, 0.75), (0, 0, 1)),
    "top": ((0.0, 0.0, 1.0), (0, 1, 0)),
    "bottom": ((0.0, 0.0, -1.0), (0, 1, 0)),
    "front": ((0.0, -1.0, 0.0), (0, 0, 1)),
    "back": ((0.0, 1.0, 0.0), (0, 0, 1)),
    "right": ((1.0, 0.0, 0.0), (0, 0, 1)),
    "left": ((-1.0, 0.0, 0.0), (0, 0, 1)),
}

EDGE_ANGLE_DEG = 24.0


LABEL_COLOR = np.array([0.82, 0.29, 0.0])


def render_3d(doc, ids, path: str, width: int = 1200, height: int = 900,
              camera=None, labels: bool = False) -> dict:
    meshes = shapes.collect_meshes(doc, ids)
    if not meshes:
        raise CadError("empty_selection", "no solids or walls to render",
                       hint="3D rendering needs solid or wall entities")

    # ---------------- camera basis
    cam = camera or "iso"
    perspective = False
    fov = 45.0
    if isinstance(cam, str):
        if cam not in VIEWS:
            raise CadError("bad_param", f"unknown view {cam!r}",
                           hint=f"named views: {sorted(VIEWS)} or "
                                '{"eye": [...], "target": [...]}')
        eye_dir, up_hint = VIEWS[cam]
        eye_dir = _unit(np.array(eye_dir, dtype=float))
        up_hint = np.array(up_hint, dtype=float)
        target = None  # fit later
    elif isinstance(cam, dict):
        eye = np.array(cam["eye"], dtype=float)
        target = np.array(cam.get("target", [0, 0, 0]), dtype=float)
        up_hint = np.array(cam.get("up", [0, 0, 1]), dtype=float)
        fov = float(cam.get("fov", 45.0))
        eye_dir = _unit(eye - target)
        perspective = True
    else:
        raise CadError("bad_param", f"cannot interpret camera {cam!r}")

    fwd = -eye_dir
    right = np.cross(fwd, up_hint)
    if np.linalg.norm(right) < 1e-9:
        right = np.cross(fwd, np.array([0.0, 1.0, 0.0]))
    right = _unit(right)
    up = _unit(np.cross(right, fwd))

    # ---------------- gather and project
    all_verts = np.concatenate([m["verts"] for m in meshes])
    center = (all_verts.min(axis=0) + all_verts.max(axis=0)) / 2
    radius = float(np.linalg.norm(all_verts.max(axis=0) - all_verts.min(axis=0))) / 2
    radius = max(radius, 1e-6)

    if perspective:
        eye_pt = eye
        look = target
    else:
        eye_pt = center + eye_dir * radius * 3.0
        look = center

    def project(verts: np.ndarray):
        rel = verts - eye_pt
        zc = rel @ fwd                      # camera depth (bigger = farther)
        uc = rel @ right
        vc = rel @ up
        if perspective:
            f = 1.0 / math.tan(math.radians(fov) / 2)
            zs = np.maximum(zc, radius * 1e-4)
            return np.stack([uc * f / zs, vc * f / zs], axis=1), zc
        return np.stack([uc, vc], axis=1), zc

    uv_all, _ = project(all_verts)
    umin, vmin = uv_all.min(axis=0)
    umax, vmax = uv_all.max(axis=0)
    du, dv = max(umax - umin, 1e-9), max(vmax - vmin, 1e-9)
    s = min(width * 0.86 / du, height * 0.86 / dv)
    ucx, vcx = (umin + umax) / 2, (vmin + vmax) / 2

    def to_px(uv: np.ndarray):
        return np.stack([width / 2 + (uv[:, 0] - ucx) * s,
                         height / 2 - (uv[:, 1] - vcx) * s], axis=1)

    canvas = Canvas(width, height, bg=(0.97, 0.97, 0.98))
    zbuf = np.full((height, width), np.inf, dtype=np.float64)
    light = _unit(-fwd * 0.8 + up * 0.5 - right * 0.25)

    # ---------------- rasterize triangles
    tri_total = 0
    for m in meshes:
        uv, zc = project(m["verts"])
        px = to_px(uv)
        tris = m["tris"]
        v3d = m["verts"]
        e1 = v3d[tris[:, 1]] - v3d[tris[:, 0]]
        e2 = v3d[tris[:, 2]] - v3d[tris[:, 0]]
        normals = np.cross(e1, e2)
        lens = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = np.divide(normals, lens, out=np.zeros_like(normals),
                            where=lens > 1e-12)
        lambert = np.clip(normals @ light, 0.0, 1.0)
        shade = 0.34 + 0.66 * lambert
        base = np.asarray(m["color"], dtype=np.float64)
        tri_total += len(tris)
        for t in range(len(tris)):
            i0, i1, i2 = tris[t]
            _raster_tri(canvas.buf, zbuf,
                        px[i0], px[i1], px[i2],
                        zc[i0], zc[i1], zc[i2],
                        base * shade[t])

        # ---------------- feature edges
        edge_color = base * 0.35
        edges = _feature_edges(v3d, tris, normals)
        bias = radius * 0.004
        for a, b in edges:
            _depth_line(canvas.buf, zbuf, px[a], px[b], zc[a], zc[b],
                        edge_color, bias)

    if labels:
        from .. import shapes as _shapes
        for m in meshes:
            c = (m["verts"].min(axis=0) + m["verts"].max(axis=0)) / 2
            uv, _ = project(c[None, :])
            px = to_px(uv)[0]
            text = _shapes.entity_label(doc, m["id"])
            canvas.line([px[0] - 4, px[1]], [px[0] + 4, px[1]], LABEL_COLOR, 1.6)
            canvas.line([px[0], px[1] - 4], [px[0], px[1] + 4], LABEL_COLOR, 1.6)
            for poly in font.text_strokes(text, [0, 0], 12.0):
                canvas.polyline([[px[0] + 6 + q[0], px[1] - 5 - q[1]]
                                 for q in poly], LABEL_COLOR, 1.3)

    _axis_gizmo(canvas, right, up, width, height)
    canvas.to_png(path)
    return {"path": path, "width": width, "height": height,
            "objects": len(meshes), "triangles": tri_total,
            "camera": cam if isinstance(cam, str) else "custom",
            "labels": bool(labels)}


# -------------------------------------------------------------- internals

def _unit(v):
    return v / np.linalg.norm(v)


def _raster_tri(buf, zbuf, p0, p1, p2, z0, z1, z2, color):
    h, w = zbuf.shape
    xmin = max(int(min(p0[0], p1[0], p2[0])), 0)
    xmax = min(int(max(p0[0], p1[0], p2[0])) + 1, w - 1)
    ymin = max(int(min(p0[1], p1[1], p2[1])), 0)
    ymax = min(int(max(p0[1], p1[1], p2[1])) + 1, h - 1)
    if xmin > xmax or ymin > ymax:
        return
    area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
    if abs(area) < 1e-9:
        return
    ys, xs = np.mgrid[ymin:ymax + 1, xmin:xmax + 1]
    xs = xs + 0.5
    ys = ys + 0.5
    w0 = ((p1[0] - xs) * (p2[1] - ys) - (p1[1] - ys) * (p2[0] - xs)) / area
    w1 = ((p2[0] - xs) * (p0[1] - ys) - (p2[1] - ys) * (p0[0] - xs)) / area
    w2 = 1.0 - w0 - w1
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= -1e-9)
    if not inside.any():
        return
    z = w0 * z0 + w1 * z1 + w2 * z2
    region_z = zbuf[ymin:ymax + 1, xmin:xmax + 1]
    visible = inside & (z < region_z)
    if not visible.any():
        return
    region_z[visible] = z[visible]
    region_c = buf[ymin:ymax + 1, xmin:xmax + 1]
    region_c[visible] = np.asarray(color, dtype=np.float32)


def _feature_edges(verts, tris, normals):
    """Edges where adjacent faces meet at a sharp angle (or boundaries)."""
    edge_faces: dict[tuple[int, int], list[int]] = {}
    for t, (a, b, c) in enumerate(tris):
        for i, j in ((a, b), (b, c), (c, a)):
            key = (i, j) if i < j else (j, i)
            edge_faces.setdefault(key, []).append(t)
    cos_limit = math.cos(math.radians(EDGE_ANGLE_DEG))
    out = []
    for (i, j), faces in edge_faces.items():
        if len(faces) == 1:
            out.append((i, j))
        elif len(faces) == 2:
            n0, n1 = normals[faces[0]], normals[faces[1]]
            if float(n0 @ n1) < cos_limit:
                out.append((i, j))
    return out


def _depth_line(buf, zbuf, p0, p1, z0, z1, color, bias):
    h, w = zbuf.shape
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    n = max(int(length), 1)
    ts = np.linspace(0.0, 1.0, n + 1)
    xs = (p0[0] + (p1[0] - p0[0]) * ts).astype(int)
    ys = (p0[1] + (p1[1] - p0[1]) * ts).astype(int)
    zs = z0 + (z1 - z0) * ts
    ok = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    xs, ys, zs = xs[ok], ys[ok], zs[ok]
    vis = zs <= zbuf[ys, xs] + bias
    buf[ys[vis], xs[vis]] = np.asarray(color, dtype=np.float32)


def _axis_gizmo(canvas, right, up, width, height):
    ox, oy = 46.0, height - 46.0
    L = 30.0
    axes = [("X", np.array([1.0, 0, 0]), (0.85, 0.2, 0.2)),
            ("Y", np.array([0, 1.0, 0]), (0.15, 0.6, 0.2)),
            ("Z", np.array([0, 0, 1.0]), (0.2, 0.35, 0.85))]
    for name, vec, color in axes:
        dx = float(vec @ right)
        dy = float(vec @ up)
        tip = [ox + dx * L, oy - dy * L]
        canvas.line([ox, oy], tip, color, 2.0)
        lbl = [tip[0] + dx * 8 - 3, tip[1] - dy * 8]
        for poly in font.glyph(name):
            pts = [[lbl[0] + gx * 9, lbl[1] - gy * 9 + 4] for gx, gy in poly]
            canvas.polyline(pts, color, 1.2)
