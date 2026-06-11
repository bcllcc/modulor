"""DXF reader: the subset that matters for taking over existing drawings.

Supported: LINE, CIRCLE, ARC, LWPOLYLINE (incl. bulges), POLYLINE/VERTEX,
TEXT, MTEXT (formatting stripped), SPLINE (fit or control points), ELLIPSE
(discretized). Layers come across with approximate colors. Everything else
is counted and reported as skipped — never silently dropped.

Works with ASCII DXF from R12 through current AutoCAD releases (the entity
group codes used here are stable across versions).
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


def read_pairs(path: str):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    pairs = []
    for i in range(0, len(lines) - 1, 2):
        code = lines[i].strip()
        if not code.lstrip("-").isdigit():
            raise CadError("bad_format", f"malformed DXF near line {i + 1}",
                           hint="binary DXF is not supported; save as ASCII DXF")
        pairs.append((int(code), lines[i + 1].strip()))
    return pairs


def import_dxf(doc, path: str, scale: float = 1.0,
               layer_prefix: str = "") -> dict:
    pairs = read_pairs(path)
    imported: dict[str, int] = {}
    skipped: dict[str, int] = {}
    created: list[str] = []
    warnings: list[str] = []
    insunits = None

    # ---- header units + layer table colors
    layer_colors: dict[str, str] = {}
    section = None
    i = 0
    while i < len(pairs):
        code, val = pairs[i]
        if code == 0 and val == "SECTION" and i + 1 < len(pairs):
            section = pairs[i + 1][1]
        elif code == 9 and val == "$INSUNITS" and i + 1 < len(pairs):
            try:
                insunits = INSUNITS.get(int(pairs[i + 1][1]))
            except ValueError:
                pass
        elif section == "TABLES" and code == 0 and val == "LAYER":
            name, color = None, None
            j = i + 1
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
        i += 1

    # ---- entities
    ents = _split_entities(pairs)
    s = scale
    for etype, codes in ents:
        try:
            n_before = len(created)
            if etype == "LINE":
                created += _add(doc, "line", {
                    "start": _pt(codes, 10, 20, s), "end": _pt(codes, 11, 21, s),
                }, codes, layer_prefix)
            elif etype == "CIRCLE":
                created += _add(doc, "circle", {
                    "center": _pt(codes, 10, 20, s),
                    "radius": _num(codes, 40) * s,
                }, codes, layer_prefix)
            elif etype == "ARC":
                created += _add(doc, "arc", {
                    "center": _pt(codes, 10, 20, s),
                    "radius": _num(codes, 40) * s,
                    "start_angle": _num(codes, 50),
                    "end_angle": _num(codes, 51),
                }, codes, layer_prefix)
            elif etype in ("LWPOLYLINE", "POLYLINE"):
                pts, closed = _polyline_points(codes, s)
                if len(pts) >= 2:
                    created += _add(doc, "polyline",
                                    {"points": pts, "closed": closed},
                                    codes, layer_prefix)
            elif etype == "TEXT":
                created += _add(doc, "text", {
                    "at": _pt(codes, 10, 20, s),
                    "text": _first(codes, 1, ""),
                    "height": _num(codes, 40) * s,
                    "rotation": _num(codes, 50, 0.0),
                }, codes, layer_prefix)
            elif etype == "MTEXT":
                created += _add(doc, "text", {
                    "at": _pt(codes, 10, 20, s),
                    "text": _strip_mtext("".join(codes.get(3, [])) +
                                         _first(codes, 1, "")),
                    "height": _num(codes, 40) * s,
                    "rotation": _num(codes, 50, 0.0),
                }, codes, layer_prefix)
            elif etype == "SPLINE":
                closed = bool(int(_first(codes, 70, "0")) & 1)
                fit = _pt_list(codes, 11, 21, s)
                ctrl = _pt_list(codes, 10, 20, s)
                pts = fit if len(fit) >= 3 else ctrl
                if len(ctrl) >= 3 and len(fit) < 3:
                    warnings.append("SPLINE without fit points: curve "
                                    "approximated through control points")
                if len(pts) >= 3:
                    created += _add(doc, "spline",
                                    {"points": pts, "closed": closed,
                                     "samples": 12}, codes, layer_prefix)
            elif etype == "ELLIPSE":
                pts, closed = _ellipse_points(codes, s)
                created += _add(doc, "polyline",
                                {"points": pts, "closed": closed},
                                codes, layer_prefix)
            else:
                skipped[etype] = skipped.get(etype, 0) + 1
                continue
            if len(created) > n_before:
                imported[etype] = imported.get(etype, 0) + 1
        except (KeyError, ValueError, IndexError) as e:
            warnings.append(f"{etype}: skipped malformed entity ({e})")
            skipped[etype] = skipped.get(etype, 0) + 1

    # ---- layer colors
    for name, color in layer_colors.items():
        lname = layer_prefix + name
        if lname in doc.layers:
            doc.layers[lname]["color"] = color

    out = {"created": created, "imported": imported, "skipped": skipped,
           "layers": sorted({doc.entities[e]["layer"] for e in created})}
    if insunits:
        out["dxf_units"] = insunits
        if insunits != doc.units and scale == 1.0:
            out["hint"] = (f"the DXF declares units {insunits!r} but this "
                           f"document uses {doc.units!r}; re-import with a "
                           "scale factor if sizes look wrong")
    if warnings:
        out["warnings"] = warnings[:20]
    return out


# ------------------------------------------------------------------ helpers

def _split_entities(pairs) -> list[tuple[str, dict]]:
    """Yield (TYPE, {code: [values...]}) for each entity in ENTITIES.

    POLYLINE absorbs its VERTEX children until SEQEND (vertex x/y/bulge are
    appended to codes 10/20/42 so they read like an LWPOLYLINE).
    """
    out = []
    section = None
    cur = None
    in_poly = False
    for idx, (code, val) in enumerate(pairs):
        if code == 0 and val == "SECTION":
            section = pairs[idx + 1][1] if idx + 1 < len(pairs) else None
            continue
        if code == 0 and val == "ENDSEC":
            section = None
            cur = None
            in_poly = False
            continue
        if section != "ENTITIES":
            continue
        if code == 0:
            if val == "VERTEX" and in_poly:
                cur = ("__vertex__", out[-1][1])  # append into the POLYLINE
                continue
            if val == "SEQEND":
                in_poly = False
                cur = None
                continue
            out.append((val, {}))
            cur = (val, out[-1][1])
            in_poly = val == "POLYLINE"
        elif cur is not None:
            cur[1].setdefault(code, []).append(val)
    return out


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
    # bulge list aligns with vertices only when every vertex carries 42;
    # most writers emit 42 only when non-zero, in which case alignment is
    # ambiguous -> we honor bulges only in the all-present case
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
    # center is perpendicular to the chord at distance d
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
    closed = abs((t1 - t0) % math.tau) < 1e-6
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


def _strip_mtext(text: str) -> str:
    text = text.replace("\\P", " ").replace("^J", " ")
    text = re.sub(r"\\[A-Za-z][^;\\{}]*;", "", text)   # \f...; \H...; \A1;
    text = re.sub(r"[{}]", "", text)
    return text.strip()


def _add(doc, etype: str, data: dict, codes: dict, prefix: str) -> list[str]:
    layer = prefix + _first(codes, 8, "0")
    return [doc.add_entity(etype, data, layer=layer)]
