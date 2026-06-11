"""Flatten document entities into a backend-neutral display list.

Primitive kinds:
  stroke  {points, closed, layer, color, width}
  circle  {center, r, layer, color, width}
  arc     {center, r, a0, a1, layer, color, width}
  fill    {contours, layer, color, outline}        # region/wall footprints
  text    {at, text, height, rotation, anchor, layer, color}

SVG/DXF keep circles/arcs/text native; the PNG rasterizer discretizes them.
"""
from __future__ import annotations

import math

import numpy as np

from .. import geometry as g
from .. import shapes
from . import font


def display_list(doc, ids) -> list[dict]:
    out = []
    for eid in ids:
        ent = doc.entities[eid]
        layer_name = ent.get("layer", "0")
        layer = doc.layers.get(layer_name, {})
        if not layer.get("visible", True):
            continue
        color = layer.get("color", "#222222")
        width = layer.get("line_width", 1.0)
        base = {"layer": layer_name, "color": color, "width": width, "id": eid}
        t = ent["type"]
        if t == "line":
            out.append({"kind": "stroke", "points": [ent["start"], ent["end"]],
                        "closed": False, **base})
        elif t == "polyline":
            out.append({"kind": "stroke", "points": list(ent["points"]),
                        "closed": bool(ent.get("closed")), **base})
        elif t == "spline":
            out.append({"kind": "stroke", "points": shapes.spline_points(ent),
                        "closed": bool(ent.get("closed")), **base})
        elif t == "circle":
            out.append({"kind": "circle", "center": ent["center"],
                        "r": ent["radius"], **base})
        elif t == "arc":
            out.append({"kind": "arc", "center": ent["center"], "r": ent["radius"],
                        "a0": ent["start_angle"], "a1": ent["end_angle"], **base})
        elif t == "region":
            out.append({"kind": "fill", "contours": ent["contours"],
                        "outline": color, **base})
        elif t == "text":
            out.append({"kind": "text", "at": ent["at"], "text": ent["text"],
                        "height": ent.get("height", 1.0),
                        "rotation": ent.get("rotation", 0.0),
                        "anchor": "start", **base})
        elif t == "dim":
            out.extend(dim_primitives(doc, ent, base))
        elif t == "dim_angular":
            out.extend(dim_angular_primitives(doc, ent, base))
        elif t == "dim_radial":
            out.extend(dim_radial_primitives(doc, ent, base))
        elif t == "wall":
            cs = shapes.wall_footprint(doc, ent)
            out.append({"kind": "fill", "contours": cs.to_polygons(),
                        "outline": color, **base})
            for sym in shapes.wall_opening_symbols(doc, ent):
                w = max(0.4, width * 0.5)
                if sym["kind"] == "line":
                    out.append({"kind": "stroke", "points": sym["points"],
                                "closed": False, **{**base, "width": w}})
                else:
                    out.append({"kind": "arc", "center": sym["center"],
                                "r": sym["radius"], "a0": sym["start"],
                                "a1": sym["end"], **{**base, "width": w}})
        elif t == "grid":
            out.extend(grid_primitives(ent, base))
        elif t == "room":
            out.extend(room_primitives(doc, ent, base))
        elif t == "solid":
            pass  # 3D bodies don't appear in 2D output
    return out


def grid_primitives(ent, base) -> list[dict]:
    xs, ys = ent["xs"], ent["ys"]
    span = max(xs[-1] - xs[0], ys[-1] - ys[0])
    ext = span * 0.04
    bub = span * 0.022
    thin = {**base, "width": max(0.35, base["width"] * 0.4)}
    prims = []
    for x, label in zip(xs, ent["x_labels"]):
        top = ys[-1] + ext
        prims.append({"kind": "stroke", "closed": False, **thin,
                      "points": [[x, ys[0] - ext], [x, top]]})
        prims.append({"kind": "circle", "center": [x, top + bub], "r": bub,
                      **thin})
        prims.append({"kind": "text", "at": [x, top + bub * 0.65],
                      "text": label, "height": bub, "rotation": 0.0,
                      "anchor": "middle", **base})
    for y, label in zip(ys, ent["y_labels"]):
        left = xs[0] - ext
        prims.append({"kind": "stroke", "closed": False, **thin,
                      "points": [[left, y], [xs[-1] + ext, y]]})
        prims.append({"kind": "circle", "center": [left - bub, y], "r": bub,
                      **thin})
        prims.append({"kind": "text", "at": [left - bub, y - bub * 0.35],
                      "text": label, "height": bub, "rotation": 0.0,
                      "anchor": "middle", **base})
    return prims


def room_primitives(doc, ent, base) -> list[dict]:
    pts = ent["points"]
    area = abs(g.polygon_area(pts))
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    th = max(math.sqrt(area) * 0.08, 1e-9)
    thin = {**base, "width": max(0.35, base["width"] * 0.5)}
    # architectural convention: report room areas in square meters
    m2 = area * (g.unit_scale(doc.units) / 1000.0) ** 2
    label = g.fmt_num(m2, 1) + " m2"
    return [
        {"kind": "stroke", "points": list(pts), "closed": True, **thin},
        {"kind": "text", "at": [cx, cy + th * 0.35], "text": ent["name"],
         "height": th, "rotation": 0.0, "anchor": "middle", **base},
        {"kind": "text", "at": [cx, cy - th * 1.05], "text": label,
         "height": th * 0.7, "rotation": 0.0, "anchor": "middle", **base},
    ]


def dim_primitives(doc, ent, base) -> list[dict]:
    """Decompose a dimension into lines, tick marks and a text primitive.

    Graphic sizes scale with the dimension offset so drawings of any scale
    stay readable.
    """
    p1, p2 = g.v2(ent["p1"]), g.v2(ent["p2"])
    off = float(ent["offset"])
    d = g.unit(p2 - p1)
    n = g.perp(d)
    k = abs(off)
    gap = 0.12 * k          # gap between measured point and extension line
    overshoot = 0.15 * k    # extension past the dimension line
    tick = 0.18 * k         # tick mark size
    th = 0.30 * k           # text height

    sgn = 1.0 if off >= 0 else -1.0
    b1 = p1 + n * off
    b2 = p2 + n * off
    prims = []
    w = max(0.4, base["width"] * 0.5)
    thin = {**base, "width": w}
    # extension lines
    for p, b in ((p1, b1), (p2, b2)):
        prims.append({"kind": "stroke", "closed": False, **thin,
                      "points": [[*(p + n * sgn * gap)],
                                 [*(b + n * sgn * overshoot)]]})
    # dimension line (slightly past the ticks, architectural style)
    prims.append({"kind": "stroke", "closed": False, **thin,
                  "points": [[*(b1 - d * overshoot)], [*(b2 + d * overshoot)]]})
    # 45-degree ticks
    tick_dir = g.unit(d + n)
    for b in (b1, b2):
        prims.append({"kind": "stroke", "closed": False, **thin,
                      "points": [[*(b - tick_dir * tick / 2)],
                                 [*(b + tick_dir * tick / 2)]]})
    # measured value
    value = ent.get("text")
    if not value:
        value = g.fmt_num(g.norm(p2 - p1), 2 if doc.units != "mm" else 0)
    ang = math.degrees(math.atan2(d[1], d[0]))
    if ang > 90.0 or ang <= -90.0:
        ang += 180.0  # keep text readable left-to-right / bottom-up
    mid = (b1 + b2) / 2 + n * sgn * (0.12 * k)
    prims.append({"kind": "text", "at": [float(mid[0]), float(mid[1])],
                  "text": value, "height": th, "rotation": ang,
                  "anchor": "middle", **base})
    return prims


def dim_angular_primitives(doc, ent, base) -> list[dict]:
    c = g.v2(ent["center"])
    v1 = g.v2(ent["p1"]) - c
    v2 = g.v2(ent["p2"]) - c
    a1 = math.degrees(math.atan2(v1[1], v1[0]))
    a2 = math.degrees(math.atan2(v2[1], v2[0]))
    sweep = (a2 - a1) % 360.0
    r = float(ent["radius"])
    w = max(0.4, base["width"] * 0.5)
    thin = {**base, "width": w}
    prims = []
    # rays from just outside the center to a bit past the arc
    for ang in (a1, a2):
        d = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
        prims.append({"kind": "stroke", "closed": False, **thin,
                      "points": [[*(c + d * r * 0.15)], [*(c + d * r * 1.1)]]})
    prims.append({"kind": "arc", "center": [*c], "r": r, "a0": a1, "a1": a2,
                  **thin})
    value = ent.get("text") or (g.fmt_num(sweep, 1) + "°")
    mid = a1 + sweep / 2
    md = np.array([math.cos(math.radians(mid)), math.sin(math.radians(mid))])
    prims.append({"kind": "text", "at": [*(c + md * r * 1.22)], "text": value,
                  "height": max(r * 0.13, 1e-9), "rotation": 0.0,
                  "anchor": "middle", **base})
    return prims


def dim_radial_primitives(doc, ent, base) -> list[dict]:
    c = g.v2(ent["center"])
    r = float(ent["radius"])
    ang = math.radians(float(ent.get("direction", 45.0)))
    d = np.array([math.cos(ang), math.sin(ang)])
    edge = c + d * r
    tip = c + d * r * 1.35
    w = max(0.4, base["width"] * 0.5)
    prims = [
        {"kind": "stroke", "closed": False, **{**base, "width": w},
         "points": [[*c], [*tip]]},
    ]
    # tick where the leader crosses the curve
    t = g.perp(d) * r * 0.06
    prims.append({"kind": "stroke", "closed": False, **{**base, "width": w},
                  "points": [[*(edge - t)], [*(edge + t)]]})
    value = ent.get("text") or ("R" + g.fmt_num(r, 2))
    prims.append({"kind": "text", "at": [*(tip + d * r * 0.05)], "text": value,
                  "height": max(r * 0.13, 1e-9), "rotation": 0.0,
                  "anchor": "start", **base})
    return prims


def discretize(prim) -> list[list[list[float]]]:
    """Reduce any display primitive to plain polylines (for raster/DXF-fallback)."""
    k = prim["kind"]
    if k == "stroke":
        pts = list(prim["points"])
        if prim.get("closed") and len(pts) > 2:
            pts = pts + [pts[0]]
        return [pts]
    if k == "circle":
        pts = g.circle_points(prim["center"], prim["r"])
        return [pts + [pts[0]]]
    if k == "arc":
        return [g.arc_points(prim["center"], prim["r"], prim["a0"], prim["a1"])]
    if k == "fill":
        return [list(c) + [list(c[0])] for c in prim["contours"]]
    if k == "text":
        return font.text_strokes(prim["text"], prim["at"], prim["height"],
                                 prim.get("rotation", 0.0),
                                 prim.get("anchor", "start"))
    return []


def display_bbox(prims) -> g.BBox:
    box = g.BBox()
    for prim in prims:
        for poly in discretize(prim):
            box.add_many(poly)
    return box
