"""Minimal DXF R12 (AC1009) writer — the most widely readable CAD exchange
format. Covers LINE, CIRCLE, ARC, LWPOLYLINE-era POLYLINE, TEXT and
BLOCK/INSERT (Modulor block instances export as native blocks); richer
entities (dims, walls, regions, hatches) are exploded to those primitives.
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

    # instances export as native INSERTs; everything else flattens to prims
    plain_ids = [e for e in ids if doc.entities[e]["type"] != "instance"]
    inst_ids = [e for e in ids if doc.entities[e]["type"] == "instance"]
    prims = flatten.display_list(doc, plain_ids)

    # blocks referenced by the exported instances, including nested ones
    block_names: list[str] = []
    queue = [doc.entities[e]["block"] for e in inst_ids]
    while queue:
        name = queue.pop(0)
        if name in block_names:
            continue
        block_names.append(name)
        for child in shapes.get_block(doc, name)["entities"]:
            if child["type"] == "instance":
                queue.append(child["block"])
    block_prims = {name: flatten.display_list_ents(
                       doc, [c for c in doc.blocks[name]["entities"]
                             if c["type"] != "instance"])
                   for name in block_names}

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
    layers = {p["layer"] for p in prims} | set(doc.layers.keys())
    for plist in block_prims.values():
        layers |= {p["layer"] for p in plist}
    layers |= {doc.entities[e].get("layer", "0") for e in inst_ids}
    layers = sorted(layers)
    code(0, "SECTION"); code(2, "TABLES")
    code(0, "TABLE"); code(2, "LAYER"); code(70, len(layers))
    for name in layers:
        color = doc.layers.get(name, {}).get("color", "#222222")
        code(0, "LAYER"); code(2, name); code(70, 0)
        code(62, _nearest_aci(shapes.parse_color(color)))
        code(6, "CONTINUOUS")
    code(0, "ENDTAB")
    code(0, "ENDSEC")

    # ---- block definitions
    if block_names:
        code(0, "SECTION"); code(2, "BLOCKS")
        for name in block_names:
            blk = doc.blocks[name]
            bx, by = blk.get("base", [0.0, 0.0])
            code(0, "BLOCK"); code(8, "0"); code(2, name); code(70, 0)
            code(10, _f(bx)); code(20, _f(by)); code(30, 0); code(3, name)
            _write_prims(code, block_prims[name])
            for child in blk["entities"]:
                if child["type"] == "instance":
                    _write_insert(code, child)
            code(0, "ENDBLK")
        code(0, "ENDSEC")

    # ---- entities
    code(0, "SECTION"); code(2, "ENTITIES")
    n = _write_prims(code, prims)
    for eid in inst_ids:
        _write_insert(code, doc.entities[eid])
        n += 1
    code(0, "ENDSEC")
    code(0, "EOF")

    with open(path, "w", encoding="ascii", errors="replace", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    out = {"path": path, "entities": n, "layers": layers}
    if block_names:
        out["blocks"] = block_names
    return out


def _write_prims(code, prims) -> int:
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
            anchor = prim.get("anchor")
            if anchor in ("middle", "end"):
                from ..render import font
                shift = font.text_width(prim["text"], prim["height"])
                x -= shift / 2 if anchor == "middle" else shift
            code(10, _f(x)); code(20, _f(y)); code(30, 0)
            code(40, _f(prim["height"])); code(1, prim["text"])
            code(50, _f(prim.get("rotation", 0.0)))
            n += 1
    return n


def _write_insert(code, ent):
    s = float(ent.get("scale", 1.0))
    code(0, "INSERT"); code(8, ent.get("layer", "0")); code(2, ent["block"])
    code(10, _f(ent["at"][0])); code(20, _f(ent["at"][1])); code(30, 0)
    code(41, _f(s)); code(42, _f(s)); code(43, _f(s))
    code(50, _f(ent.get("rotation", 0.0)))


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
