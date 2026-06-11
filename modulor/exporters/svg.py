"""SVG export: faithful 2D output with native circles/arcs/text, grouped by layer."""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

from .. import geometry as g
from ..render import flatten


def export_svg(doc, ids, path: str, margin_frac: float = 0.05) -> dict:
    svg, meta = svg_string(doc, ids, margin_frac)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return {"path": path, **meta}


def svg_string(doc, ids, margin_frac: float = 0.05) -> tuple[str, dict]:
    prims = flatten.display_list(doc, ids)
    box = flatten.display_bbox(prims)
    if box.empty:
        box.add([0, 0])
        box.add([100, 100])
    size = box.size()
    margin = max(size[0], size[1]) * margin_frac or 10.0
    x0 = box.min[0] - margin
    y0 = box.min[1] - margin
    w = size[0] + 2 * margin
    h = size[1] + 2 * margin

    # stroke width that prints hairline-thin regardless of drawing extents
    base_w = max(w, h) / 900.0

    by_layer: dict[str, list[str]] = {}
    for prim in prims:
        by_layer.setdefault(prim["layer"], []).append(_prim_svg(prim, base_w))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{_f(x0)} {_f(-(y0 + h))} {_f(w)} {_f(h)}" '
        f'width="{_f(w)}{_svg_unit(doc.units)}" height="{_f(h)}{_svg_unit(doc.units)}">',
        # CAD is y-up, SVG is y-down: flip once at the root
        '<g transform="scale(1,-1)">',
        f'<rect x="{_f(x0)}" y="{_f(y0)}" width="{_f(w)}" height="{_f(h)}" '
        f'fill="white"/>',
    ]
    for layer, items in by_layer.items():
        parts.append(f'<g data-layer="{escape(layer)}">')
        parts.extend(items)
        parts.append('</g>')
    parts.append('</g></svg>')
    svg = "\n".join(parts)
    return svg, {"primitives": len(prims),
                 "viewbox": [round(x0, 3), round(y0, 3),
                             round(w, 3), round(h, 3)]}


def _prim_svg(prim, base_w: float) -> str:
    k = prim["kind"]
    color = prim["color"]
    sw = _f(base_w * prim.get("width", 1.0))
    common = f'stroke="{color}" stroke-width="{sw}" fill="none" ' \
             f'stroke-linecap="round" stroke-linejoin="round"'
    if k == "stroke":
        pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in prim["points"])
        tag = "polygon" if prim.get("closed") else "polyline"
        return f'<{tag} points="{pts}" {common}/>'
    if k == "circle":
        c = prim["center"]
        return f'<circle cx="{_f(c[0])}" cy="{_f(c[1])}" r="{_f(prim["r"])}" ' \
               f'{common}/>'
    if k == "arc":
        return f'<path d="{_arc_path(prim)}" {common}/>'
    if k == "fill":
        d = []
        for c in prim["contours"]:
            d.append("M " + " L ".join(f"{_f(x)},{_f(y)}" for x, y in c) + " Z")
        return f'<path d="{" ".join(d)}" fill="{color}" fill-opacity="0.25" ' \
               f'fill-rule="nonzero" stroke="{prim.get("outline", color)}" ' \
               f'stroke-width="{sw}"/>'
    if k == "text":
        x, y = prim["at"]
        h = prim["height"]
        rot = prim.get("rotation", 0.0)
        anchor = {"start": "start", "middle": "middle"}[prim.get("anchor", "start")]
        # un-flip the y axis locally so glyphs are upright
        tf = f'translate({_f(x)},{_f(y)}) rotate({_f(rot)}) scale(1,-1)'
        return (f'<text transform="{tf}" font-size="{_f(h * 1.35)}" '
                f'font-family="ui-monospace, Consolas, monospace" '
                f'text-anchor="{anchor}" fill="{color}" stroke="none">'
                f'{escape(prim["text"])}</text>')
    return ""


def _arc_path(prim) -> str:
    cx, cy = prim["center"]
    r = prim["r"]
    a0, a1 = prim["a0"], prim["a1"]
    sweep = (a1 - a0) % 360.0 or 360.0
    if sweep >= 360.0 - 1e-9:  # full circle as two arcs
        sweep = 359.99
    x0 = cx + r * math.cos(math.radians(a0))
    y0 = cy + r * math.sin(math.radians(a0))
    x1 = cx + r * math.cos(math.radians(a0 + sweep))
    y1 = cy + r * math.sin(math.radians(a0 + sweep))
    large = 1 if sweep > 180.0 else 0
    return f"M {_f(x0)},{_f(y0)} A {_f(r)} {_f(r)} 0 {large} 1 {_f(x1)},{_f(y1)}"


def _svg_unit(units: str) -> str:
    return {"mm": "mm", "cm": "cm", "in": "in", "m": "", "ft": ""}.get(units, "")


def _f(v: float) -> str:
    return g.fmt_num(float(v), 4)
