"""Render the 2D drawing to a PNG image (plan view, white background)."""
from __future__ import annotations

import numpy as np

from .. import shapes
from . import flatten, font
from .raster import Canvas


LABEL_COLOR = (0.82, 0.29, 0.0)  # orange overlay, distinct from drawing inks


def render_2d(doc, ids, path: str, width: int = 1200, height: int = 900,
              labels: bool = False) -> dict:
    prims = flatten.display_list(doc, ids)
    box = flatten.display_bbox(prims)
    if box.empty:
        box.add([0, 0])
        box.add([100, 100])

    size = box.size()
    margin = 0.05
    sx = width * (1 - 2 * margin) / max(size[0], 1e-9)
    sy = height * (1 - 2 * margin) / max(size[1], 1e-9)
    s = min(sx, sy)
    cx, cy = box.center()[:2]

    def to_px(p):
        return [width / 2 + (p[0] - cx) * s,
                height / 2 - (p[1] - cy) * s]  # flip y

    canvas = Canvas(width, height)
    base_px = max(1.0, min(width, height) / 800.0)

    fills = [p for p in prims if p["kind"] == "fill"]
    others = [p for p in prims if p["kind"] != "fill"]

    for prim in fills:
        color = np.asarray(shapes.parse_color(prim["color"]))
        light = color * 0.25 + 0.75  # pastel fill, full-strength outline
        contours_px = [[to_px(q) for q in c] for c in prim["contours"]]
        canvas.fill_polygon(contours_px, light)
        for c in contours_px:
            canvas.polyline(c + [c[0]], color, base_px * prim.get("width", 1.0))

    for prim in others:
        color = shapes.parse_color(prim["color"])
        if prim["kind"] == "text":
            h = prim["height"]
            strokes = font.text_strokes(prim["text"], prim["at"], h,
                                        prim.get("rotation", 0.0),
                                        prim.get("anchor", "start"))
            wpx = max(1.0, h * s / 14.0)
            for poly in strokes:
                canvas.polyline([to_px(q) for q in poly], color, wpx)
        else:
            wpx = base_px * prim.get("width", 1.0)
            for poly in flatten.discretize(prim):
                canvas.polyline([to_px(q) for q in poly], color, wpx)

    if labels:
        lh = 11.0  # label height in pixels: readable at any drawing scale
        for eid in ids:
            if doc.entities[eid]["type"] == "solid":
                continue
            a = shapes.entity_anchor(doc, eid)
            px = to_px(a)
            _label(canvas, shapes.entity_label(doc, eid), px, lh)

    canvas.to_png(path)
    return {"path": path, "width": width, "height": height,
            "primitives": len(prims), "labels": bool(labels)}


def _label(canvas, text: str, px, height_px: float):
    """Pixel-space entity label: a small cross marker + stroke-font text.

    font.text_strokes works in y-up coordinates; pixels are y-down, so the
    glyph y is mirrored around the text baseline.
    """
    canvas.line([px[0] - 3, px[1]], [px[0] + 3, px[1]], LABEL_COLOR, 1.6)
    canvas.line([px[0], px[1] - 3], [px[0], px[1] + 3], LABEL_COLOR, 1.6)
    ax, ay = px[0] + 5, px[1] - 4  # baseline anchor, above-right of the cross
    for poly in font.text_strokes(text, [0, 0], height_px):
        canvas.polyline([[ax + q[0], ay - q[1]] for q in poly],
                        LABEL_COLOR, 1.2)
