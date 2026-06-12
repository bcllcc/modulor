"""DXF reader: the subset that matters for taking over existing drawings.

Supported: LINE, CIRCLE, ARC, LWPOLYLINE (incl. bulges), POLYLINE/VERTEX,
TEXT, MTEXT (formatting stripped), SPLINE (fit or control points), ELLIPSE
(discretized), INSERT (block references: nested, scaled, rotated, row/column
arrays), DIMENSION (via its rendered anonymous block), HATCH (polyline /
line / arc boundary loops as regions). Layers come across with approximate
colors. Everything else is counted and reported as skipped — never silently
dropped.

Text handling: R2007+ files are UTF-8; older files are decoded via the
$DWGCODEPAGE header (GBK, Shift-JIS, ...). \\U+XXXX escapes and the legacy
%%c/%%d/%%p codes are resolved.
"""
from __future__ import annotations

import math
import re

from .. import geometry as g
from ..document import DEFAULT_LAYER
from ..errors import CadError

# approximate AutoCAD color index -> hex (the common low indices)
ACI_HEX = {1: "#ff0000", 2: "#ffff00", 3: "#00ff00", 4: "#00ffff",
           5: "#0000ff", 6: "#ff00ff", 7: "#282828", 8: "#808080",
           9: "#c0c0c0", 30: "#ff7f00", 250: "#333333", 251: "#505050",
           252: "#696969", 253: "#828282", 254: "#bebebe", 256: "#222222"}

INSUNITS = {0: None, 1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}

# $DWGCODEPAGE -> python codec (pre-R2007 files; newer ones are UTF-8)
CODEPAGES = {"ANSI_936": "gbk", "ANSI_932": "shift_jis", "ANSI_949": "cp949",
             "ANSI_950": "big5", "ANSI_1251": "cp1251", "ANSI_1252": "cp1252",
             "ANSI_1250": "cp1250", "ANSI_1254": "cp1254"}

MAX_BLOCK_DEPTH = 5
MAX_EXPANDED_ENTITIES = 50_000


def read_pairs(path: str):
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"AutoCAD Binary DXF"):
        raise CadError("bad_format", "binary DXF is not supported",
                       hint="save as ASCII DXF")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        codec = "cp1252"
        m = re.search(rb"\$DWGCODEPAGE[\r\n]+\s*3[\r\n]+\s*([A-Za-z0-9_]+)",
                      raw[:16000], re.I)
        if m:
            codec = CODEPAGES.get(m.group(1).decode("ascii", "replace").upper(),
                                  "cp1252")
        text = raw.decode(codec, errors="replace")
    lines = text.splitlines()
    pairs = []
    for i in range(0, len(lines) - 1, 2):
        code = lines[i].strip()
        if not code.lstrip("-").isdigit():
            raise CadError("bad_format", f"malformed DXF near line {i + 1}",
                           hint="binary DXF is not supported; save as ASCII DXF")
        pairs.append((int(code), lines[i + 1].strip()))
    return pairs


def import_dxf(doc, path: str, scale: float = 1.0,
               layer_prefix: str = "", blocks: str = "native") -> dict:
    pairs = read_pairs(path)
    ctx = _Ctx(doc, scale, layer_prefix, blocks_mode=blocks)

    # ---- header units + layer table colors
    layer_colors: dict[str, str] = {}
    section = None
    for idx, (code, val) in enumerate(pairs):
        if code == 0 and val == "SECTION" and idx + 1 < len(pairs):
            section = pairs[idx + 1][1]
        elif code == 9 and val == "$INSUNITS" and idx + 1 < len(pairs):
            try:
                ctx.insunits = INSUNITS.get(int(pairs[idx + 1][1]))
            except ValueError:
                pass
        elif section == "TABLES" and code == 0 and val == "LAYER":
            name, color = None, None
            j = idx + 1
            while j < len(pairs) and pairs[j][0] != 0:
                if pairs[j][0] == 2:
                    name = pairs[j][1]
                elif pairs[j][0] == 62:
                    try:
                        color = ACI_HEX.get(abs(int(pairs[j][1])))
                    except ValueError:
                        pass
                j += 1
            if name:
                layer_colors[name] = color or DEFAULT_LAYER["color"]

    # ---- blocks + entities
    ctx.blocks, entities = _split_sections(pairs)
    for etype, codes, raw in entities:
        ctx.convert(etype, codes, raw, depth=0)

    for name, color in layer_colors.items():
        lname = layer_prefix + name
        if lname in doc.layers:
            doc.layers[lname]["color"] = color

    out = {"created": ctx.created, "imported": ctx.imported,
           "skipped": ctx.skipped,
           "layers": sorted({doc.entities[e]["layer"] for e in ctx.created
                             if e in doc.entities})}
    defined = sorted(v for v in ctx.defined_blocks.values() if v)
    if defined:
        out["blocks"] = defined
    if ctx.insunits:
        out["dxf_units"] = ctx.insunits
        if ctx.insunits != doc.units and scale == 1.0:
            out["hint"] = (f"the DXF declares units {ctx.insunits!r} but this "
                           f"document uses {doc.units!r}; re-import with a "
                           "scale factor if sizes look wrong")
    if ctx.warnings:
        out["warnings"] = ctx.warnings[:20]
    return out


# ------------------------------------------------------------------ sections

def _split_sections(pairs):
    """Returns (blocks, entities).

    blocks:   name -> {"base": [x, y], "records": [(etype, codes, raw)]}
    entities: [(etype, codes, raw)] from the ENTITIES section.
    codes is {group_code: [values...]}; raw is the ordered (code, value)
    list (needed by HATCH, whose loops are order-sensitive).
    POLYLINE absorbs its VERTEX children in both places.
    """
    blocks: dict[str, dict] = {}
    entities: list = []
    section = None
    cur = None            # (codes, raw) of the record being filled
    block = None          # current block dict when inside BLOCK..ENDBLK
    in_poly = False

    def start(etype, target):
        nonlocal cur
        codes: dict = {}
        raw: list = []
        target.append((etype, codes, raw))
        cur = (codes, raw)

    for idx, (code, val) in enumerate(pairs):
        if code == 0 and val == "SECTION":
            section = pairs[idx + 1][1] if idx + 1 < len(pairs) else None
            cur = block = None
            in_poly = False
            continue
        if code == 0 and val == "ENDSEC":
            section = None
            cur = block = None
            in_poly = False
            continue

        if section == "BLOCKS":
            if code == 0 and val == "BLOCK":
                block = {"base": [0.0, 0.0], "records": [], "_name": None}
                cur = ("block-header", block)
                continue
            if code == 0 and val == "ENDBLK":
                if block and block["_name"]:
                    blocks[block["_name"]] = block
                block = None
                cur = None
                in_poly = False
                continue
            if block is None:
                continue
            if isinstance(cur, tuple) and cur[0] == "block-header":
                if code == 2 and not block["_name"]:
                    block["_name"] = val
                elif code == 10:
                    block["base"][0] = _f(val)
                elif code == 20:
                    block["base"][1] = _f(val)
                if code == 0:
                    pass  # falls through below to start a record
                else:
                    continue
            if code == 0:
                if val == "VERTEX" and in_poly and block["records"]:
                    cur = (block["records"][-1][1], block["records"][-1][2])
                    continue
                if val == "SEQEND":
                    in_poly = False
                    cur = None
                    continue
                start(val, block["records"])
                in_poly = val == "POLYLINE"
            elif cur is not None and not (isinstance(cur, tuple)
                                          and cur[0] == "block-header"):
                cur[0].setdefault(code, []).append(val)
                cur[1].append((code, val))
            continue

        if section == "ENTITIES":
            if code == 0:
                if val == "VERTEX" and in_poly and entities:
                    cur = (entities[-1][1], entities[-1][2])
                    continue
                if val == "SEQEND":
                    in_poly = False
                    cur = None
                    continue
                start(val, entities)
                in_poly = val == "POLYLINE"
            elif cur is not None:
                cur[0].setdefault(code, []).append(val)
                cur[1].append((code, val))

    return blocks, entities


# ------------------------------------------------------------------ context

class _Ctx:
    """Conversion state; block expansion recurses through it."""

    def __init__(self, doc, scale: float, layer_prefix: str,
                 blocks_mode: str = "native"):
        self.doc = doc
        self.scale = scale
        self.prefix = layer_prefix
        self.blocks: dict[str, dict] = {}
        self.blocks_mode = blocks_mode      # "native" | "explode"
        self.defined_blocks: dict[str, str] = {}  # dxf name -> doc block name
        self.imported: dict[str, int] = {}
        self.skipped: dict[str, int] = {}
        self.created: list[str] = []
        self.warnings: list[str] = []
        self.insunits = None

    def warn(self, msg: str):
        if len(self.warnings) < 40:
            self.warnings.append(msg)

    def convert(self, etype, codes, raw, depth) -> list[str]:
        """Top-level record -> document entities, with honest accounting."""
        try:
            ids = self._convert(etype, codes, raw, depth)
        except (KeyError, ValueError, IndexError) as e:
            self.warn(f"{etype}: skipped malformed entity ({e})")
            self.skipped[etype] = self.skipped.get(etype, 0) + 1
            return []
        if ids is None:
            self.skipped[etype] = self.skipped.get(etype, 0) + 1
            return []
        if ids:
            self.imported[etype] = self.imported.get(etype, 0) + 1
            self.created.extend(ids)
        return ids

    def _convert(self, etype, codes, raw, depth):
        s = self.scale
        if etype == "LINE":
            return self._add("line", {"start": _pt(codes, 10, 20, s),
                                      "end": _pt(codes, 11, 21, s)}, codes)
        if etype == "CIRCLE":
            return self._add("circle", {"center": _pt(codes, 10, 20, s),
                                        "radius": _num(codes, 40) * s}, codes)
        if etype == "ARC":
            return self._add("arc", {"center": _pt(codes, 10, 20, s),
                                     "radius": _num(codes, 40) * s,
                                     "start_angle": _num(codes, 50),
                                     "end_angle": _num(codes, 51)}, codes)
        if etype in ("LWPOLYLINE", "POLYLINE"):
            pts, closed = _polyline_points(codes, s)
            if len(pts) < 2:
                return []
            return self._add("polyline", {"points": pts, "closed": closed},
                             codes)
        if etype == "TEXT":
            return self._add("text", {
                "at": _pt(codes, 10, 20, s),
                "text": _decode_text(_first(codes, 1, "")),
                "height": _num(codes, 40) * s,
                "rotation": _num(codes, 50, 0.0)}, codes)
        if etype == "MTEXT":
            return self._add("text", {
                "at": _pt(codes, 10, 20, s),
                "text": _strip_mtext("".join(codes.get(3, []))
                                     + _first(codes, 1, "")),
                "height": _num(codes, 40) * s,
                "rotation": _num(codes, 50, 0.0)}, codes)
        if etype == "SPLINE":
            closed = bool(int(_first(codes, 70, "0")) & 1)
            fit = _pt_list(codes, 11, 21, s)
            ctrl = _pt_list(codes, 10, 20, s)
            pts = fit if len(fit) >= 3 else ctrl
            if len(ctrl) >= 3 and len(fit) < 3:
                self.warn("SPLINE without fit points: curve approximated "
                          "through control points")
            if len(pts) < 3:
                return []
            return self._add("spline", {"points": pts, "closed": closed,
                                        "samples": 12}, codes)
        if etype == "ELLIPSE":
            t0 = _num(codes, 41, 0.0)
            t1 = _num(codes, 42, math.tau)
            span = (t1 - t0) % math.tau
            if span < 1e-4 or span > math.tau - 1e-4:  # full ellipse: native
                mx = float(_first(codes, 11)) * s
                my = float(_first(codes, 21)) * s
                major = math.hypot(mx, my)
                ratio = _num(codes, 40)
                if major > 0 and ratio > 0:
                    return self._add("ellipse", {
                        "center": _pt(codes, 10, 20, s),
                        "rx": major, "ry": major * ratio,
                        "rotation": math.degrees(math.atan2(my, mx))},
                        codes)
            pts, closed = _ellipse_points(codes, s)  # elliptical arc
            return self._add("polyline", {"points": pts, "closed": closed},
                             codes)
        if etype == "INSERT":
            return self._insert(codes, depth)
        if etype == "LEADER":
            pts = _pt_list(codes, 10, 20, s)
            if len(pts) < 2:
                return []
            return self._add("polyline", {"points": pts, "closed": False},
                             codes)
        if etype == "DIMENSION":
            name = _first(codes, 2, "")
            if name and name in self.blocks:
                return self._instantiate(name, g.mat2_identity(), depth)
            return None
        if etype == "HATCH":
            return self._hatch(codes, raw)
        return None  # unsupported -> counted as skipped

    def _add(self, etype, data, codes):
        layer = self.prefix + _first(codes, 8, "0")
        return [self.doc.add_entity(etype, data, layer=layer)]

    # ---- block references --------------------------------------------

    def _insert(self, codes, depth):
        name = _first(codes, 2)
        if name not in self.blocks:
            self.warn(f"INSERT references unknown block {name!r}")
            return []
        if depth >= MAX_BLOCK_DEPTH:
            self.warn(f"INSERT {name!r}: nesting deeper than "
                      f"{MAX_BLOCK_DEPTH}, skipped")
            return []
        s = self.scale
        ins = _pt(codes, 10, 20, s)
        sx = _num(codes, 41, 1.0)
        sy = _num(codes, 42, 1.0)
        rot = _num(codes, 50, 0.0)
        cols = max(1, int(_num(codes, 70, 1)))
        rows = max(1, int(_num(codes, 71, 1)))
        dx = _num(codes, 44, 0.0) * s
        dy = _num(codes, 45, 0.0) * s

        # semantic path: a uniformly scaled reference to a named block
        # becomes a native instance; anything an instance cannot express
        # (non-uniform or mirrored scale) falls back to expansion
        if (self.blocks_mode == "native" and not name.startswith("*")
                and abs(sx - sy) < 1e-9 and sx > 0):
            doc_name = self._ensure_block(name, depth)
            if doc_name is not None:
                ids = []
                cr, sr = _cos_sin(rot)
                for r_i in range(rows):
                    for c_i in range(cols):
                        ox, oy = c_i * dx * sx, r_i * dy * sy
                        at = [ins[0] + ox * cr - oy * sr,
                              ins[1] + ox * sr + oy * cr]
                        ids.append(self.doc.add_entity(
                            "instance",
                            {"block": doc_name, "at": at, "rotation": rot,
                             "scale": sx},
                            layer=self.prefix + _first(codes, 8, "0")))
                return ids

        ids = []
        for r_i in range(rows):
            for c_i in range(cols):
                # column/row offsets apply in the block's rotated frame
                m = g.mat2_translate(*ins)
                m = m @ g.mat2_rotate(rot)
                m = m @ g.mat2_translate(c_i * dx, r_i * dy)
                m = m @ g.mat2_scale(sx, sy)
                ids.extend(self._instantiate(name, m, depth))
                if len(self.created) + len(ids) > MAX_EXPANDED_ENTITIES:
                    self.warn("INSERT expansion exceeded the entity budget")
                    return ids
        return ids

    def _ensure_block(self, name, depth):
        """Convert a DXF block definition into a document block (once).
        Returns the document block name, or None if conversion failed."""
        if name in self.defined_blocks:
            return self.defined_blocks[name]
        block = self.blocks[name]
        # convert records into the document, then detach them into the
        # definition; nested INSERTs become nested instances recursively
        ids: list[str] = []
        for etype, codes, raw in block["records"]:
            try:
                sub = self._convert(etype, codes, raw, depth + 1)
            except (KeyError, ValueError, IndexError) as e:
                self.warn(f"block {name!r}/{etype}: skipped ({e})")
                continue
            if sub:
                ids.extend(sub)
        entities = [self.doc.entities.pop(eid) for eid in ids
                    if eid in self.doc.entities]
        if not entities:
            self.warn(f"block {name!r} is empty after conversion; "
                      "references are expanded instead")
            self.defined_blocks[name] = None
            return None
        doc_name = name.replace("/", "_")
        k = 2
        while doc_name in self.doc.blocks:
            doc_name = f"{name.replace('/', '_')}~{k}"
            k += 1
        base = block["base"]
        self.doc.blocks[doc_name] = {
            "base": [base[0] * self.scale, base[1] * self.scale],
            "entities": entities,
        }
        self.defined_blocks[name] = doc_name
        return doc_name

    def _instantiate(self, name, m, depth) -> list[str]:
        """Create one transformed copy of a block's entities."""
        from ..ops.transform import _transform_entity
        block = self.blocks[name]
        base = block["base"]
        m_total = m @ g.mat2_translate(-base[0] * self.scale,
                                       -base[1] * self.scale)
        ids: list[str] = []
        for etype, codes, raw in block["records"]:
            try:
                sub = self._convert(etype, codes, raw, depth + 1)
            except (KeyError, ValueError, IndexError) as e:
                self.warn(f"block {name!r}/{etype}: skipped ({e})")
                continue
            if sub:
                ids.extend(sub)
        kept = []
        for eid in ids:
            try:
                _transform_entity(self.doc, eid, m_total)
                kept.append(eid)
            except CadError as e:
                # e.g. non-uniformly scaled circle: drop honestly
                self.warn(f"block {name!r}: dropped {eid} ({e.message[:60]})")
                self.doc.delete_entities([eid])
        return kept

    # ---- hatches -------------------------------------------------------

    def _hatch(self, codes, raw):
        """Boundary loops -> region. Polyline, line and arc edges are
        supported; loops with ellipse/spline edges skip the whole hatch."""
        s = self.scale
        contours = []
        i = 0
        n = len(raw)

        def num_at(j):
            return float(raw[j][1])

        while i < n:
            code, val = raw[i]
            if code != 92:           # loop start flag
                i += 1
                continue
            loop_flag = int(float(val))
            external = bool(loop_flag & 1)
            pts: list[list[float]] = []
            if loop_flag & 2:        # polyline path
                has_bulge = False
                count = 0
                i += 1
                while i < n and raw[i][0] not in (92, 75, 76, 98):
                    c, v = raw[i]
                    if c == 72:
                        has_bulge = bool(int(float(v)))
                    elif c == 93:
                        count = int(float(v))
                    elif c == 10:
                        x = float(v) * s
                        y = float(raw[i + 1][1]) * s \
                            if i + 1 < n and raw[i + 1][0] == 20 else 0.0
                        bulge = 0.0
                        if has_bulge and i + 2 < n and raw[i + 2][0] == 42:
                            bulge = float(raw[i + 2][1])
                        if pts and bulge == 0.0:
                            pass
                        pts.append([x, y])
                        if bulge:
                            pts.append(("bulge", bulge))  # marker
                    i += 1
                pts = _resolve_hatch_bulges(pts)
                _ = count
            else:                    # edge list
                edges = int(float(raw[i + 1][1])) \
                    if i + 1 < n and raw[i + 1][0] == 93 else 0
                i += 2
                ok = True
                for _e in range(edges):
                    while i < n and raw[i][0] != 72:
                        i += 1
                    if i >= n:
                        ok = False
                        break
                    etype = int(float(raw[i][1]))
                    i += 1
                    fields = {}
                    while i < n and raw[i][0] not in (72, 92, 97, 98):
                        c, v = raw[i]
                        fields.setdefault(c, []).append(float(v))
                        i += 1
                    if etype == 1:   # line
                        pts.append([fields[10][0] * s, fields[20][0] * s])
                        pts.append([fields[11][0] * s, fields[21][0] * s])
                    elif etype == 2:  # arc
                        cx, cy = fields[10][0] * s, fields[20][0] * s
                        r = fields[40][0] * s
                        a0, a1 = fields[50][0], fields[51][0]
                        ccw = bool(int(fields.get(73, [1])[0]))
                        if not ccw:
                            a0, a1 = 360 - a0, 360 - a1
                            a0, a1 = a1, a0
                        pts.extend(g.arc_points([cx, cy], r, a0, a1))
                    else:            # ellipse/spline edges: punt honestly
                        ok = False
                        break
                if not ok:
                    return None
            if len(pts) >= 3:
                contour = g.ensure_ccw(pts)
                if not external:
                    contour = contour[::-1]  # holes wind clockwise
                contours.append(contour)
            # NOTE: i already advanced past this loop

        if not contours:
            return None
        return self._add("region", {"contours": contours}, codes)


def _resolve_hatch_bulges(pts):
    """Replace ('bulge', b) markers with arc interpolation points."""
    out = []
    i = 0
    while i < len(pts):
        p = pts[i]
        if isinstance(p, list):
            out.append(p)
            i += 1
            continue
        # marker follows its start vertex; the end vertex is the next list
        _tag, b = p
        start = out[-1] if out else None
        j = i + 1
        while j < len(pts) and not isinstance(pts[j], list):
            j += 1
        end = pts[j] if j < len(pts) else (out[0] if out else None)
        if start and end:
            out.extend(_bulge_arc(start, end, b))
        i += 1
    return out


# ------------------------------------------------------------------ helpers

def _f(v) -> float:
    return float(v)


def _cos_sin(deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    return math.cos(a), math.sin(a)


def _first(codes: dict, code: int, default=None):
    vals = codes.get(code)
    if not vals:
        if default is None:
            raise KeyError(f"group code {code} missing")
        return default
    return vals[0]


def _num(codes: dict, code: int, default=None) -> float:
    return float(_first(codes, code, default))


def _pt(codes: dict, cx: int, cy: int, s: float) -> list[float]:
    return [float(_first(codes, cx)) * s, float(_first(codes, cy)) * s]


def _pt_list(codes: dict, cx: int, cy: int, s: float) -> list[list[float]]:
    xs = codes.get(cx, [])
    ys = codes.get(cy, [])
    return [[float(x) * s, float(y) * s] for x, y in zip(xs, ys)]


def _polyline_points(codes: dict, s: float):
    closed = bool(int(_first(codes, 70, "0")) & 1)
    xs = codes.get(10, [])
    ys = codes.get(20, [])
    bulges = codes.get(42, [])
    use_bulge = len(bulges) == len(xs) and any(float(b) != 0 for b in bulges)
    pts = []
    n = len(xs)
    for i in range(n):
        p = [float(xs[i]) * s, float(ys[i]) * s]
        pts.append(p)
        if use_bulge and (i + 1 < n or closed):
            b = float(bulges[i])
            if abs(b) > 1e-12:
                q_x = float(xs[(i + 1) % n]) * s
                q_y = float(ys[(i + 1) % n]) * s
                pts.extend(_bulge_arc(p, [q_x, q_y], b))
    return pts, closed


def _bulge_arc(p1, p2, bulge: float, max_seg: int = 16) -> list[list[float]]:
    """Intermediate points of a bulged segment (excluding both endpoints)."""
    sweep = 4.0 * math.atan(bulge)
    chord = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if chord < 1e-12:
        return []
    radius = chord / (2.0 * math.sin(abs(sweep) / 2.0))
    mid = [(p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0]
    d = math.sqrt(max(radius * radius - (chord / 2.0) ** 2, 0.0))
    nx = -(p2[1] - p1[1]) / chord
    ny = (p2[0] - p1[0]) / chord
    side = 1.0 if sweep > 0 else -1.0
    cx = mid[0] + nx * d * side * (1 if abs(sweep) <= math.pi else -1)
    cy = mid[1] + ny * d * side * (1 if abs(sweep) <= math.pi else -1)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    segs = max(2, min(max_seg, int(abs(sweep) / math.radians(15)) + 1))
    return [[cx + radius * math.cos(a1 + sweep * t / segs),
             cy + radius * math.sin(a1 + sweep * t / segs)]
            for t in range(1, segs)]


def _ellipse_points(codes: dict, s: float):
    c = _pt(codes, 10, 20, s)
    mx = float(_first(codes, 11)) * s
    my = float(_first(codes, 21)) * s
    ratio = _num(codes, 40)
    t0 = _num(codes, 41, 0.0)
    t1 = _num(codes, 42, math.tau)
    span = (t1 - t0) % math.tau
    closed = span < 1e-4 or span > math.tau - 1e-4
    major = math.hypot(mx, my)
    ang = math.atan2(my, mx)
    n = 48
    span = (t1 - t0) % math.tau or math.tau
    pts = []
    steps = n if closed else n + 1
    for i in range(steps):
        t = t0 + span * i / n
        x = major * math.cos(t)
        y = major * ratio * math.sin(t)
        pts.append([c[0] + x * math.cos(ang) - y * math.sin(ang),
                    c[1] + x * math.sin(ang) + y * math.cos(ang)])
    return pts, closed


_UNICODE_ESC = re.compile(r"\\[Uu]\+([0-9A-Fa-f]{4})")


def _decode_text(text: str) -> str:
    text = _UNICODE_ESC.sub(lambda m: chr(int(m.group(1), 16)), text)
    text = (text.replace("%%c", "⌀").replace("%%C", "⌀")
                .replace("%%d", "°").replace("%%D", "°")
                .replace("%%p", "±").replace("%%P", "±")
                .replace("%%%", "%"))
    return text


def _strip_mtext(text: str) -> str:
    text = text.replace("\\P", " ").replace("^J", " ")
    text = re.sub(r"\\[A-Za-z][^;\\{}]*;", "", text)   # \f...; \H...; \A1;
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\^.", "", text)                    # caret control codes
    return _decode_text(text).strip()
