"""Minimal DXF R12 (AC1009) writer — the most widely readable CAD exchange
format. Covers LINE, CIRCLE, ARC, LWPOLYLINE-era POLYLINE, and TEXT; richer
entities (dims, walls, regions) are exploded to those primitives.
"""
from __future__ import annotations

from ..render import flatten

# AutoCAD color index approximations for layer colors
_ACI = [
    (1, (255, 0, 0)), (2, (255, 255, 0)), (3, (0, 255, 0)),
    (4, (0, 255, 255)), (5, (0, 0, 255)), (6, (255, 0, 255)),
    (7, (40, 40, 40)), (8, (128, 128, 128)), (9, (192, 192, 192)),
]


def export_dxf(doc, ids, path: str) -> dict:
    from .. import shapes

    prims = flatten.display_list(doc, ids)
    lines: list[str] = []
    w = lines.append

    def code(c, v):
        w(str(c))
        w(str(v))

    # ---- header
    code(0, "SECTION"); code(2, "HEADER")
    code(9, "$ACADVER"); code(1, "AC1009")
    code(0, "ENDSEC")

    # ---- layer table
    layers = sorted({p["layer"] for p in prims} | set(doc.layers.keys()))
    code(0, "SECTION"); code(2, "TABLES")
    code(0, "TABLE"); code(2, "LAYER"); code(70, len(layers))
    for name in layers:
        color = doc.layers.get(name, {}).get("color", "#222222")
        code(0, "LAYER"); code(2, name); code(70, 0)
        code(62, _nearest_aci(shapes.parse_color(color)))
        code(6, "CONTINUOUS")
    code(0, "ENDTAB")
    code(0, "ENDSEC")

    # ---- entities
    code(0, "SECTION"); code(2, "ENTITIES")
    n = 0
    for prim in prims:
        k = prim["kind"]
        layer = prim["layer"]
        if k == "stroke":
            pts = prim["points"]
            if len(pts) == 2 and not prim.get("closed"):
                code(0, "LINE"); code(8, layer)
                code(10, _f(pts[0][0])); code(20, _f(pts[0][1])); code(30, 0)
                code(11, _f(pts[1][0])); code(21, _f(pts[1][1])); code(31, 0)
            else:
                _polyline(code, layer, pts, prim.get("closed", False))
            n += 1
        elif k == "circle":
            code(0, "CIRCLE"); code(8, layer)
            code(10, _f(prim["center"][0])); code(20, _f(prim["center"][1]))
            code(30, 0); code(40, _f(prim["r"]))
            n += 1
        elif k == "arc":
            code(0, "ARC"); code(8, layer)
            code(10, _f(prim["center"][0])); code(20, _f(prim["center"][1]))
            code(30, 0); code(40, _f(prim["r"]))
            code(50, _f(prim["a0"] % 360)); code(51, _f(prim["a1"] % 360))
            n += 1
        elif k == "fill":
            for c in prim["contours"]:
                _polyline(code, layer, c, True)
                n += 1
        elif k == "text":
            code(0, "TEXT"); code(8, layer)
            x, y = prim["at"]
            if prim.get("anchor") == "middle":
                from ..render import font
                x -= font.text_width(prim["text"], prim["height"]) / 2
            code(10, _f(x)); code(20, _f(y)); code(30, 0)
            code(40, _f(prim["height"])); code(1, prim["text"])
            code(50, _f(prim.get("rotation", 0.0)))
            n += 1
    code(0, "ENDSEC")
    code(0, "EOF")

    with open(path, "w", encoding="ascii", errors="replace", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return {"path": path, "entities": n, "layers": layers}


def _polyline(code, layer, pts, closed: bool):
    code(0, "POLYLINE"); code(8, layer); code(66, 1)
    code(70, 1 if closed else 0)
    for x, y in pts:
        code(0, "VERTEX"); code(8, layer)
        code(10, _f(x)); code(20, _f(y)); code(30, 0)
    code(0, "SEQEND")


def _nearest_aci(rgb) -> int:
    r, gg, b = [v * 255 for v in rgb]
    best, best_d = 7, 1e18
    for idx, (cr, cg, cb) in _ACI:
        d = (r - cr) ** 2 + (gg - cg) ** 2 + (b - cb) ** 2
        if d < best_d:
            best, best_d = idx, d
    return best


def _f(v) -> str:
    return f"{float(v):.6f}".rstrip("0").rstrip(".")
