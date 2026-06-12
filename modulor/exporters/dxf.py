"""DXF R2000 (AC1015) writer — semantic fidelity into the Autodesk world.

Entities export as their native DXF counterparts, editable in AutoCAD:
ellipse -> ELLIPSE, spline -> SPLINE (fit points), hatch -> HATCH
(user-defined pattern / solid), dims -> associative DIMENSION with a
rendered anonymous *D block, leader -> LEADER, polyline -> LWPOLYLINE,
region/wall footprints -> solid HATCH + boundary, blocks -> BLOCK/INSERT.
Walls, grids and rooms have no DXF concept and explode to primitives.

Hand-written on purpose: zero runtime dependencies, auditable output.
The test suite validates every exported file with ezdxf (recover + audit).
"""
from __future__ import annotations

import math

from ..render import flatten

# AutoCAD color index approximations for layer colors
_ACI = [
    (1, (255, 0, 0)), (2, (255, 255, 0)), (3, (0, 255, 0)),
    (4, (0, 255, 255)), (5, (0, 0, 255)), (6, (255, 0, 255)),
    (7, (40, 40, 40)), (8, (128, 128, 128)), (9, (192, 192, 192)),
    (250, (51, 51, 51)), (251, (80, 80, 80)), (252, (105, 105, 105)),
    (253, (130, 130, 130)), (254, (190, 190, 190)),
]

_INSUNITS = {"mm": 4, "cm": 5, "m": 6, "in": 1, "ft": 2}


class _W:
    """Tagged-value writer with a monotonic handle allocator."""

    def __init__(self):
        self.lines: list[str] = []
        self._next = 0x2F

    def code(self, c, v):
        self.lines.append(str(c))
        self.lines.append(str(v))

    def h(self) -> str:
        self._next += 1
        return format(self._next, "X")

    def seed(self) -> str:
        return format(self._next + 1, "X")


def export_dxf(doc, ids, path: str) -> dict:
    from .. import shapes

    w = _W()
    code = w.code

    ents = [(eid, doc.entities[eid]) for eid in ids]

    # ---- collect referenced blocks (transitively, definition order)
    block_names: list[str] = []
    queue = [e["block"] for _, e in ents if e["type"] == "instance"]
    while queue:
        name = queue.pop(0)
        if name in block_names:
            continue
        block_names.append(name)
        for child in shapes.get_block(doc, name)["entities"]:
            if child["type"] == "instance":
                queue.append(child["block"])

    # ---- allocate an anonymous block per dimension entity
    dim_blocks: dict[str, str] = {}  # eid -> *D name
    n_anon = 0
    for eid, ent in ents:
        if ent["type"] in ("dim", "dim_angular", "dim_radial"):
            n_anon += 1
            dim_blocks[eid] = f"*D{n_anon}"

    # ---- layers (document + everything reachable)
    layers = set(doc.layers.keys()) | {e.get("layer", "0") for _, e in ents}
    for name in block_names:
        layers |= {c.get("layer", "0")
                   for c in doc.blocks[name]["entities"]}
    layers = sorted(layers)

    # ================================================== HEADER
    code(0, "SECTION"); code(2, "HEADER")
    code(9, "$ACADVER"); code(1, "AC1015")
    code(9, "$DWGCODEPAGE"); code(3, "ANSI_1252")
    code(9, "$INSUNITS"); code(70, _INSUNITS.get(doc.units, 4))
    seed_pos = len(w.lines)  # patched at the end
    code(9, "$HANDSEED"); code(5, "FFFF")
    code(0, "ENDSEC")

    # ================================================== TABLES
    code(0, "SECTION"); code(2, "TABLES")

    def table(name, records, record_writer, handle_code=5):
        th = w.h()
        code(0, "TABLE"); code(2, name); code(5, th); code(330, 0)
        code(100, "AcDbSymbolTable"); code(70, len(records))
        for rec in records:
            rh = w.h()
            code(0, name); code(handle_code, rh); code(330, th)
            code(100, "AcDbSymbolTableRecord")
            record_writer(rec, rh)
        code(0, "ENDTAB")
        return th

    def vport(rec, rh):
        code(100, "AcDbViewportTableRecord"); code(2, rec); code(70, 0)
        code(10, 0); code(20, 0); code(11, 1); code(21, 1)
        code(12, 0); code(22, 0); code(40, 1000); code(41, 1.5)
    table("VPORT", ["*Active"], vport)

    def ltype(rec, rh):
        code(100, "AcDbLinetypeTableRecord"); code(2, rec); code(70, 0)
        code(3, "Solid line" if rec == "CONTINUOUS" else "")
        code(72, 65); code(73, 0); code(40, 0)
    table("LTYPE", ["ByBlock", "ByLayer", "CONTINUOUS"], ltype)

    def layer_rec(rec, rh):
        color = doc.layers.get(rec, {}).get("color", "#222222")
        code(100, "AcDbLayerTableRecord"); code(2, rec); code(70, 0)
        code(62, _nearest_aci(shapes.parse_color(color)))
        code(6, "CONTINUOUS"); code(370, -3); code(390, "F")
    table("LAYER", layers, layer_rec)

    def style(rec, rh):
        code(100, "AcDbTextStyleTableRecord"); code(2, rec); code(70, 0)
        code(40, 0); code(41, 1); code(50, 0); code(71, 0)
        code(42, 2.5); code(3, "txt"); code(4, "")
    table("STYLE", ["Standard"], style)

    table("VIEW", [], lambda r, h: None)
    table("UCS", [], lambda r, h: None)

    def appid(rec, rh):
        code(100, "AcDbRegAppTableRecord"); code(2, rec); code(70, 0)
    table("APPID", ["ACAD"], appid)

    def dimstyle(rec, rh):
        code(100, "AcDbDimStyleTableRecord"); code(2, rec); code(70, 0)
    th = w.h()
    code(0, "TABLE"); code(2, "DIMSTYLE"); code(5, th); code(330, 0)
    code(100, "AcDbSymbolTable"); code(70, 1)
    code(100, "AcDbDimStyleTable")
    rh = w.h()
    code(0, "DIMSTYLE"); code(105, rh); code(330, th)
    code(100, "AcDbSymbolTableRecord")
    dimstyle("Standard", rh)
    code(0, "ENDTAB")

    # BLOCK_RECORD: model/paper space + user blocks + dim blocks
    brh: dict[str, str] = {}
    all_blocks = (["*Model_Space", "*Paper_Space"] + block_names
                  + [dim_blocks[k] for k in dim_blocks])
    th = w.h()
    code(0, "TABLE"); code(2, "BLOCK_RECORD"); code(5, th); code(330, 0)
    code(100, "AcDbSymbolTable"); code(70, len(all_blocks))
    for name in all_blocks:
        rh = w.h()
        brh[name] = rh
        code(0, "BLOCK_RECORD"); code(5, rh); code(330, th)
        code(100, "AcDbSymbolTableRecord")
        code(100, "AcDbBlockTableRecord"); code(2, name); code(340, 0)
    code(0, "ENDTAB")
    code(0, "ENDSEC")

    msp = brh["*Model_Space"]
    counter = {"n": 0}

    # -------------------------------------------------- entity emitters

    def ehead(dxf_type, layer, owner):
        code(0, dxf_type); code(5, w.h()); code(330, owner)
        code(100, "AcDbEntity"); code(8, layer)

    def e_line(p0, p1, layer, owner):
        ehead("LINE", layer, owner); code(100, "AcDbLine")
        code(10, _f(p0[0])); code(20, _f(p0[1])); code(30, 0)
        code(11, _f(p1[0])); code(21, _f(p1[1])); code(31, 0)

    def e_lwpoly(pts, closed, layer, owner):
        ehead("LWPOLYLINE", layer, owner); code(100, "AcDbPolyline")
        code(90, len(pts)); code(70, 1 if closed else 0)
        for x, y in pts:
            code(10, _f(x)); code(20, _f(y))

    def e_circle(c, r, layer, owner):
        ehead("CIRCLE", layer, owner); code(100, "AcDbCircle")
        code(10, _f(c[0])); code(20, _f(c[1])); code(30, 0); code(40, _f(r))

    def e_arc(c, r, a0, a1, layer, owner):
        ehead("ARC", layer, owner); code(100, "AcDbCircle")
        code(10, _f(c[0])); code(20, _f(c[1])); code(30, 0); code(40, _f(r))
        code(100, "AcDbArc")
        code(50, _f(a0 % 360)); code(51, _f(a1 % 360))

    def e_text(at, text, height, rotation, layer, owner):
        ehead("TEXT", layer, owner); code(100, "AcDbText")
        code(10, _f(at[0])); code(20, _f(at[1])); code(30, 0)
        code(40, _f(height)); code(1, text)
        if rotation:
            code(50, _f(rotation))
        code(7, "Standard")
        code(100, "AcDbText")

    def e_ellipse(ent, layer, owner):
        rx, ry = float(ent["rx"]), float(ent["ry"])
        rot = math.radians(float(ent.get("rotation", 0.0)))
        if ry > rx:  # DXF wants ratio <= 1: swap axes
            rx, ry = ry, rx
            rot += math.pi / 2
        ehead("ELLIPSE", layer, owner); code(100, "AcDbEllipse")
        code(10, _f(ent["center"][0])); code(20, _f(ent["center"][1]))
        code(30, 0)
        code(11, _f(rx * math.cos(rot))); code(21, _f(rx * math.sin(rot)))
        code(31, 0)
        code(40, _f(ry / rx))
        code(41, 0); code(42, _f(2 * math.pi))

    def e_spline(ent, layer, owner):
        pts = ent["points"]
        closed = bool(ent.get("closed"))
        ehead("SPLINE", layer, owner); code(100, "AcDbSpline")
        code(210, 0); code(220, 0); code(230, 1)
        code(70, (1 if closed else 0) | 8)  # planar
        code(71, 3); code(72, 0); code(73, 0); code(74, len(pts))
        code(42, "0.000000001"); code(43, "0.0000000001")
        code(44, "0.0000000001")
        for x, y in pts:
            code(11, _f(x)); code(21, _f(y)); code(31, 0)

    def e_hatch(contours, layer, owner, solid=True, pattern=None):
        ehead("HATCH", layer, owner); code(100, "AcDbHatch")
        code(10, 0); code(20, 0); code(30, 0)
        code(210, 0); code(220, 0); code(230, 1)
        code(2, "SOLID" if solid else "MODULOR")
        code(70, 1 if solid else 0)
        code(71, 0)
        code(91, len(contours))
        for c in contours:
            code(92, 2)            # polyline boundary
            code(72, 0)            # no bulges
            code(73, 1)            # closed
            code(93, len(c))
            for x, y in c:
                code(10, _f(x)); code(20, _f(y))
            code(97, 0)
        code(75, 0)                # normal hatch style
        code(76, 1 if solid else 0)  # predefined / user-defined
        if not solid:
            spacing, angles = pattern
            code(52, 0); code(41, 1); code(77, 0)
            code(78, len(angles))
            for a in angles:
                ar = math.radians(a)
                code(53, _f(a))
                code(43, 0); code(44, 0)
                code(45, _f(-math.sin(ar) * spacing))
                code(46, _f(math.cos(ar) * spacing))
                code(79, 0)
        code(98, 0)

    def e_leader(ent, layer, owner):
        ehead("LEADER", layer, owner); code(100, "AcDbLeader")
        code(3, "Standard")
        code(71, 1); code(72, 0); code(73, 3)
        code(76, len(ent["points"]))
        for x, y in ent["points"]:
            code(10, _f(x)); code(20, _f(y)); code(30, 0)
        # the label is a plain TEXT continuing the last segment
        import numpy as np
        from .. import geometry as g
        h = float(ent.get("height", 1.0))
        end = np.asarray(ent["points"][-1], dtype=float)
        d = g.unit(end - np.asarray(ent["points"][-2], dtype=float))
        at = end + d * h * 0.4
        e_text([float(at[0]), float(at[1]) - h * 0.35], ent["text"], h,
               0.0, layer, owner)

    def e_dimension(eid, ent, layer, owner):
        from .. import geometry as g
        import numpy as np
        t = ent["type"]
        ehead("DIMENSION", layer, owner)
        code(100, "AcDbDimension")
        code(2, dim_blocks[eid])
        if t == "dim":
            p1 = np.asarray(ent["p1"], dtype=float)
            p2 = np.asarray(ent["p2"], dtype=float)
            off = float(ent["offset"])
            n = g.perp(g.unit(p2 - p1))
            dl = p2 + n * off
            mid = (p1 + p2) / 2 + n * off
            code(10, _f(dl[0])); code(20, _f(dl[1])); code(30, 0)
            code(11, _f(mid[0])); code(21, _f(mid[1])); code(31, 0)
            code(70, 1 | 32)
            if ent.get("text"):
                code(1, ent["text"])
            code(3, "Standard")
            code(100, "AcDbAlignedDimension")
            code(13, _f(p1[0])); code(23, _f(p1[1])); code(33, 0)
            code(14, _f(p2[0])); code(24, _f(p2[1])); code(34, 0)
        elif t == "dim_angular":
            c = np.asarray(ent["center"], dtype=float)
            v1 = np.asarray(ent["p1"], dtype=float)
            v2 = np.asarray(ent["p2"], dtype=float)
            r = float(ent["radius"])
            a1 = math.atan2(v1[1] - c[1], v1[0] - c[0])
            a2 = math.atan2(v2[1] - c[1], v2[0] - c[0])
            sweep = (a2 - a1) % (2 * math.pi)
            am = a1 + sweep / 2
            arcp = c + np.array([math.cos(am), math.sin(am)]) * r
            code(10, _f(arcp[0])); code(20, _f(arcp[1])); code(30, 0)
            code(11, _f(arcp[0])); code(21, _f(arcp[1])); code(31, 0)
            code(70, 5 | 32)
            if ent.get("text"):
                code(1, ent["text"])
            code(3, "Standard")
            code(100, "AcDb3PointAngularDimension")
            code(13, _f(v1[0])); code(23, _f(v1[1])); code(33, 0)
            code(14, _f(v2[0])); code(24, _f(v2[1])); code(34, 0)
            code(15, _f(c[0])); code(25, _f(c[1])); code(35, 0)
        else:  # dim_radial
            c = np.asarray(ent["center"], dtype=float)
            r = float(ent["radius"])
            a = math.radians(float(ent.get("direction", 45.0)))
            edge = c + np.array([math.cos(a), math.sin(a)]) * r
            code(10, _f(c[0])); code(20, _f(c[1])); code(30, 0)
            tip = c + np.array([math.cos(a), math.sin(a)]) * r * 1.35
            code(11, _f(tip[0])); code(21, _f(tip[1])); code(31, 0)
            code(70, 4 | 32)
            if ent.get("text"):
                code(1, ent["text"])
            code(3, "Standard")
            code(100, "AcDbRadialDimension")
            code(15, _f(edge[0])); code(25, _f(edge[1])); code(35, 0)
            code(40, _f(r * 0.35))

    def e_insert(ent, owner):
        ehead("INSERT", ent.get("layer", "0"), owner)
        code(100, "AcDbBlockReference")
        code(2, ent["block"])
        code(10, _f(ent["at"][0])); code(20, _f(ent["at"][1])); code(30, 0)
        s = float(ent.get("scale", 1.0))
        code(41, _f(s)); code(42, _f(s)); code(43, _f(s))
        code(50, _f(ent.get("rotation", 0.0)))

    def emit_prims(prims, owner):
        n = 0
        for prim in prims:
            k = prim["kind"]
            layer = prim["layer"]
            if k == "stroke":
                pts = prim["points"]
                if len(pts) == 2 and not prim.get("closed"):
                    e_line(pts[0], pts[1], layer, owner)
                else:
                    e_lwpoly(pts, prim.get("closed", False), layer, owner)
                n += 1
            elif k == "circle":
                e_circle(prim["center"], prim["r"], layer, owner)
                n += 1
            elif k == "arc":
                e_arc(prim["center"], prim["r"], prim["a0"], prim["a1"],
                      layer, owner)
                n += 1
            elif k == "fill":
                e_hatch(prim["contours"], layer, owner, solid=True)
                for c in prim["contours"]:
                    e_lwpoly(c, True, layer, owner)
                n += 1
            elif k == "text":
                x, y = prim["at"]
                anchor = prim.get("anchor")
                if anchor in ("middle", "end"):
                    from ..render import font
                    shift = font.text_width(prim["text"], prim["height"])
                    x -= shift / 2 if anchor == "middle" else shift
                e_text([x, y], prim["text"], prim["height"],
                       prim.get("rotation", 0.0), layer, owner)
                n += 1
        return n

    def emit_entity(eid, ent, owner):
        t = ent["type"]
        layer = ent.get("layer", "0")
        if t == "line":
            e_line(ent["start"], ent["end"], layer, owner)
        elif t == "polyline":
            e_lwpoly(ent["points"], bool(ent.get("closed")), layer, owner)
        elif t == "spline":
            e_spline(ent, layer, owner)
        elif t == "circle":
            e_circle(ent["center"], ent["radius"], layer, owner)
        elif t == "arc":
            e_arc(ent["center"], ent["radius"], ent["start_angle"],
                  ent["end_angle"], layer, owner)
        elif t == "ellipse":
            e_ellipse(ent, layer, owner)
        elif t == "region":
            e_hatch(ent["contours"], layer, owner, solid=True)
            for c in ent["contours"]:
                e_lwpoly(c, True, layer, owner)
        elif t == "hatch":
            if ent.get("pattern") == "solid":
                e_hatch(ent["contours"], layer, owner, solid=True)
            else:
                angles = [float(ent.get("angle", 45.0))]
                if ent.get("pattern") == "cross":
                    angles.append(angles[0] + 90.0)
                e_hatch(ent["contours"], layer, owner, solid=False,
                        pattern=(float(ent["spacing"]), angles))
            for c in ent["contours"]:
                e_lwpoly(c, True, layer, owner)
        elif t == "text":
            e_text(ent["at"], ent["text"], ent.get("height", 1.0),
                   ent.get("rotation", 0.0), layer, owner)
        elif t == "leader":
            e_leader(ent, layer, owner)
        elif t in ("dim", "dim_angular", "dim_radial"):
            e_dimension(eid, ent, layer, owner)
        elif t == "instance":
            e_insert(ent, owner)
        elif t == "solid":
            return 0  # 3D bodies don't appear in 2D exchange
        else:  # wall / grid / room: no DXF concept, explode to primitives
            return emit_prims(flatten.ent_prims(doc, eid, ent), owner)
        return 1

    # ================================================== BLOCKS
    code(0, "SECTION"); code(2, "BLOCKS")

    def block_shell(name, base, body):
        rec = brh[name]
        anonymous = name.startswith("*D")
        code(0, "BLOCK"); code(5, w.h()); code(330, rec)
        code(100, "AcDbEntity"); code(8, "0")
        code(100, "AcDbBlockBegin")
        code(2, name); code(70, 1 if anonymous else 0)
        code(10, _f(base[0])); code(20, _f(base[1])); code(30, 0)
        code(3, name); code(1, "")
        body(rec)
        code(0, "ENDBLK"); code(5, w.h()); code(330, rec)
        code(100, "AcDbEntity"); code(8, "0")
        code(100, "AcDbBlockEnd")

    block_shell("*Model_Space", [0, 0], lambda rec: None)
    block_shell("*Paper_Space", [0, 0], lambda rec: None)
    for name in block_names:
        blk = doc.blocks[name]

        def body(rec, blk=blk):
            for child in blk["entities"]:
                if child["type"] == "instance":
                    e_insert(child, rec)
                else:
                    emit_entity("b", child, rec)
        block_shell(name, blk.get("base", [0, 0]), body)
    for eid, bname in dim_blocks.items():

        def body(rec, eid=eid):
            emit_prims(flatten.ent_prims(doc, eid, doc.entities[eid]), rec)
        block_shell(bname, [0, 0], body)
    code(0, "ENDSEC")

    # ================================================== ENTITIES
    code(0, "SECTION"); code(2, "ENTITIES")
    for eid, ent in ents:
        counter["n"] += emit_entity(eid, ent, msp)
    code(0, "ENDSEC")

    # ================================================== OBJECTS
    code(0, "SECTION"); code(2, "OBJECTS")
    root = w.h(); child = w.h()
    code(0, "DICTIONARY"); code(5, root); code(330, 0)
    code(100, "AcDbDictionary"); code(281, 1)
    code(3, "ACAD_GROUP"); code(350, child)
    code(0, "DICTIONARY"); code(5, child); code(330, root)
    code(100, "AcDbDictionary"); code(281, 1)
    code(0, "ENDSEC")
    code(0, "EOF")

    # patch $HANDSEED with the real next handle
    w.lines[seed_pos + 3] = w.seed()

    with open(path, "w", encoding="ascii", errors="replace",
              newline="\r\n") as f:
        f.write("\n".join(w.lines) + "\n")
    out = {"path": path, "entities": counter["n"], "layers": layers}
    if block_names:
        out["blocks"] = block_names
    return out


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
