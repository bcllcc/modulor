"""Architectural semantics: grid, room/program, roof, stair, facade, surface.

These are deliberately *generators and annotations*, not a BIM object model:
a roof op emits an ordinary solid, a facade emits ordinary solids, a room is
an annotated polygon. Everything stays inspectable, boolean-able and
exportable — no special cases downstream.
"""
from __future__ import annotations

import math
import string

import numpy as np
from manifold3d import CrossSection, FillRule, Manifold, OpType

from .. import geometry as g
from .. import shapes
from ..errors import CadError
from . import P, op
from .model3d import _add_solid, _solid_result


def _k(doc) -> float:
    """mm-equivalent scale: defaults stay sensible in any unit system."""
    return 1.0 / g.unit_scale(doc.units)


# ------------------------------------------------------------------ grid

@op("add_grid",
    doc="Structural grid: labeled axis lines drawn in plan. Reference "
        "intersections anywhere a number is accepted: grid_x('B'), "
        "grid_y('3'). Axes can be explicit coordinates or "
        '{"start", "count", "spacing"} (spacing may be an expression).',
    params={
        "x": P.obj(req=True, doc='[0, 4000, 8000] or '
                                 '{"start": 0, "count": 5, "spacing": "bay"}'),
        "y": P.obj(req=True, doc="same for the y axis"),
        "x_labels": P.array(doc="default A, B, C, ..."),
        "y_labels": P.array(doc="default 1, 2, 3, ..."),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_grid",
             "x": {"start": 0, "count": 5, "spacing": "bay"},
             "y": [0, 6000, 12000]},
    returns="{created: [id], x, y}")
def add_grid(doc, p):
    xs = _axis_coords(doc, p["x"], "x")
    ys = _axis_coords(doc, p["y"], "y")
    xl = [str(v) for v in p["x_labels"]] if p["x_labels"] else \
        list(string.ascii_uppercase[:len(xs)])
    yl = [str(v) for v in p["y_labels"]] if p["y_labels"] else \
        [str(i + 1) for i in range(len(ys))]
    if len(xl) < len(xs) or len(yl) < len(ys):
        raise CadError("bad_param", "not enough labels for the grid lines")
    eid = doc.add_entity("grid", {"xs": xs, "ys": ys,
                                  "x_labels": xl[:len(xs)],
                                  "y_labels": yl[:len(ys)]},
                         layer=p["layer"] or "grid", tag=p["tag"])
    return {"created": [eid], "x": dict(zip(xl, xs)), "y": dict(zip(yl, ys))}


def _axis_coords(doc, spec, axis) -> list[float]:
    if isinstance(spec, list):
        coords = [doc.resolve(v) for v in spec]
    elif isinstance(spec, dict):
        try:
            start = doc.resolve(spec.get("start", 0))
            count = int(round(doc.resolve(spec["count"])))
            spacing = doc.resolve(spec["spacing"])
        except KeyError as e:
            raise CadError("bad_param", f"grid {axis} axis is missing {e}")
        if count < 2 or count > 200:
            raise CadError("bad_param", "grid count should be 2..200")
        coords = [start + spacing * i for i in range(count)]
    else:
        raise CadError("bad_param", f"grid {axis} should be a coordinate "
                                    'list or {"start","count","spacing"}')
    if len(coords) < 2 or any(b <= a for a, b in zip(coords, coords[1:])):
        raise CadError("bad_param", f"grid {axis} coordinates must be "
                                    "strictly increasing (>= 2 of them)")
    return [float(c) for c in coords]


# ------------------------------------------------------------------ rooms

@op("add_room",
    doc="Declare a room/zone/site: a named program area. It renders as a "
        "boundary + name + live area label in plan, and feeds the "
        "'program' report. Boundary can be points or an existing closed "
        "shape.",
    params={
        "name": P.string(req=True, doc="room/zone name"),
        "points": P.points(doc="boundary polygon (or use 'boundary')"),
        "boundary": P.select(doc="existing closed shape to take the "
                                 "boundary from"),
        "level": P.string(doc="level name (for the program report)"),
        "kind": P.enum(["room", "zone", "site"], default="room",
               doc="rooms count toward the program area"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_room", "name": "LIVING", "level": "L1",
             "points": [[0, 0], [5000, 0], [5000, 4000], [0, 4000]]},
    returns="{created: [id], area}")
def add_room(doc, p):
    pts = p["points"]
    if pts is None and p["boundary"] is not None:
        ids = doc.select(p["boundary"])
        if len(ids) != 1:
            raise CadError("bad_target", "boundary must match exactly 1 entity")
        contours = shapes.entity_contours(doc, doc.entities[ids[0]])
        if len(contours) != 1:
            raise CadError("bad_target", "boundary shape must be a single "
                                         "contour (no holes)")
        pts = contours[0]
    if pts is None or len(pts) < 3:
        raise CadError("missing_param", "room needs 'points' or 'boundary'")
    pts = g.ensure_ccw(pts)
    data = {"name": p["name"], "points": pts, "kind": p["kind"]}
    if p["level"]:
        data["level"] = p["level"]
    eid = doc.add_entity("room", data, layer=p["layer"] or "rooms",
                         tag=p["tag"])
    return {"created": [eid], "area": round(g.polygon_area(pts), 6)}


@op("program",
    doc="The area program: every room/zone/site with its level and area, "
        "plus totals by kind and by name. The brief-checking report.",
    params={},
    example={"op": "program"},
    returns="{rooms: [...], total_area, by_name, by_level}", effects="none")
def program(doc, p):
    rows = []
    by_name: dict[str, float] = {}
    by_level: dict[str, float] = {}
    total = 0.0
    m2 = (g.unit_scale(doc.units) / 1000.0) ** 2
    for eid, ent in doc.entities.items():
        if ent["type"] != "room":
            continue
        area = abs(g.polygon_area(ent["points"]))
        row = {"id": eid, "name": ent["name"], "kind": ent.get("kind", "room"),
               "area": round(area, 6), "area_m2": round(area * m2, 2)}
        if ent.get("level"):
            row["level"] = ent["level"]
            by_level[ent["level"]] = by_level.get(ent["level"], 0) + area
        rows.append(row)
        by_name[ent["name"]] = by_name.get(ent["name"], 0) + area
        if ent.get("kind", "room") == "room":
            total += area
    return {"rooms": rows,
            "total_room_area": round(total, 6),
            "by_name": {k: round(v, 6) for k, v in by_name.items()},
            "by_level": {k: round(v, 6) for k, v in by_level.items()},
            "units": f"{doc.units}^2"}


# ------------------------------------------------------------------ roof

@op("add_roof",
    doc="Generate a roof solid over a closed footprint: 'flat' slab, "
        "'shed' single slope, or 'gable' double slope with a central "
        "ridge. direction sets the ridge/slope orientation in degrees.",
    params={
        "footprint": P.select(req=True, doc="closed 2D shape"),
        "kind": P.enum(["flat", "shed", "gable"], default="gable",
               doc="roof shape"),
        "pitch": P.number(default=30.0, doc="slope, degrees (5-75)"),
        "thickness": P.number(doc="slab thickness (default 200mm eq.)"),
        "overhang": P.number(default=0.0, doc="eave extension beyond the "
                                              "footprint"),
        "z": P.number(default=0.0, doc="eave elevation (expressions: "
                                       "\"level_top('L2')\")"),
        "direction": P.number(default=0.0, doc="ridge axis (gable) or "
                                               "downhill axis (shed), degrees"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_roof", "footprint": {"tags": ["plan"]},
             "kind": "gable", "pitch": 35, "overhang": 600,
             "z": "level_top('L2')"},
    returns="{created: [id], ridge_height, volume, bbox}")
def add_roof(doc, p):
    ids = doc.select(p["footprint"])
    if not ids:
        raise CadError("empty_selection", "footprint matched nothing")
    contours = []
    for eid in ids:
        contours.extend(shapes.entity_contours(doc, doc.entities[eid]))
    cs = CrossSection(contours, FillRule.Positive)
    if p["overhang"]:
        cs = cs.offset(p["overhang"], _round_join())
    thickness = p["thickness"] or 200 * _k(doc)
    if p["kind"] == "flat":
        man = Manifold.extrude(cs, thickness).translate((0, 0, p["z"]))
        sid = _add_solid(doc, man, p, default_layer="roof")
        return {**_solid_result(doc, sid), "ridge_height": round(thickness, 6)}

    if not 5 <= p["pitch"] <= 75:
        raise CadError("bad_param", "pitch should be 5..75 degrees")
    ang = p["direction"]
    cs_r = cs.rotate(-ang)
    x0, y0, x1, y1 = cs_r.bounds()
    thk_v = thickness / math.cos(math.radians(p["pitch"]))
    slope = math.tan(math.radians(p["pitch"]))
    if p["kind"] == "gable":
        ymid = (y0 + y1) / 2
        h = slope * (ymid - y0)
        profile = [[y0, 0], [ymid, h], [y1, 0],
                   [y1, thk_v], [ymid, h + thk_v], [y0, thk_v]]
    else:  # shed: rises toward +y of the rotated frame
        h = slope * (y1 - y0)
        profile = [[y0, 0], [y1, h], [y1, h + thk_v], [y0, thk_v]]
    span = (x1 - x0) + 2
    wedge = Manifold.extrude(
        CrossSection([g.ensure_ccw(profile)], FillRule.Positive), span)
    # extruded space (u=profile y, v=profile z, w=length) -> rotated frame
    remap = np.array([[0, 0, 1, x0 - 1],
                      [1, 0, 0, 0],
                      [0, 1, 0, 0]], dtype=float)
    wedge = wedge.transform(remap)
    prism = Manifold.extrude(cs_r, h + thk_v + 2).translate((0, 0, -1))
    roof = (prism ^ wedge).rotate((0, 0, ang)).translate((0, 0, p["z"]))
    if roof.is_empty():
        raise CadError("empty_result", "roof construction produced nothing",
                       hint="check footprint size vs pitch")
    sid = _add_solid(doc, roof, p, default_layer="roof")
    return {**_solid_result(doc, sid), "ridge_height": round(h + thk_v, 6)}


def _round_join():
    from manifold3d import JoinType
    return JoinType.Round


# ------------------------------------------------------------------ stair

@op("add_stair",
    doc="Straight stair flight as a solid. Riser/tread are computed from "
        "the rise using the comfort rule (2R + T = 630mm eq.) and reported "
        "back; the flight runs along +X from 'at' before rotation.",
    params={
        "at": P.point2(req=True, doc="start of the first riser"),
        "rise": P.number(req=True, doc="total height (e.g. "
                                       "\"level('L2')-level('L1')\")"),
        "width": P.number(doc="flight width (default 1100mm eq.)"),
        "direction": P.number(default=0.0, doc="run direction, degrees"),
        "z": P.number(default=0.0, doc="base elevation"),
        "riser_max": P.number(doc="max riser height (default 180mm eq.)"),
        "tread": P.number(doc="tread depth (default from comfort rule)"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_stair", "at": [1000, 500], "rise": 3200,
             "direction": 90},
    returns="{created: [id], risers, riser, tread, run}")
def add_stair(doc, p):
    k = _k(doc)
    if p["rise"] <= 0:
        raise CadError("bad_param", "rise must be positive")
    width = p["width"] or 1100 * k
    riser_max = p["riser_max"] or 180 * k
    n = max(2, math.ceil(p["rise"] / riser_max))
    if n > 500:
        raise CadError("over_budget", f"{n} risers exceeds the 500 budget",
                       hint="raise riser_max or reduce the rise")
    riser = p["rise"] / n
    tread = p["tread"] or min(max(630 * k - 2 * riser, 240 * k), 350 * k)
    boxes = []
    for i in range(n):
        boxes.append(Manifold.cube((tread, width, (i + 1) * riser))
                     .translate((i * tread, 0, 0)))
    man = Manifold.batch_boolean(boxes, OpType.Add)
    man = man.rotate((0, 0, p["direction"]))
    man = man.translate((p["at"][0], p["at"][1], p["z"]))
    sid = _add_solid(doc, man, p, default_layer="stairs")
    return {**_solid_result(doc, sid), "risers": n,
            "riser": round(riser, 3), "tread": round(tread, 3),
            "run": round(n * tread, 3)}


# ------------------------------------------------------------------ facade

@op("add_facade",
    doc="Curtain-wall facade between two plan points: a mullion grid solid "
        "plus a glass pane solid. Panel sizes come from cols/rows or from "
        "target spacing.",
    params={
        "start": P.point2(req=True),
        "end": P.point2(req=True),
        "height": P.number(req=True, doc="facade height (> 0)"),
        "z": P.number(default=0.0, doc="sill elevation"),
        "cols": P.integer(doc="panel columns (default: by spacing)"),
        "rows": P.integer(doc="panel rows (default: by spacing)"),
        "spacing": P.number(doc="target panel size (default 1500mm eq.)"),
        "mullion": P.number(doc="mullion face width (default 60mm eq.)"),
        "depth": P.number(doc="mullion depth (default 120mm eq.)"),
        "mullion_material": P.material(),
        "glass_material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_facade", "start": [0, 0], "end": [12000, 0],
             "height": 8000, "spacing": 2000},
    returns="{created: [mullions, glass], cols, rows, panel}")
def add_facade(doc, p):
    k = _k(doc)
    a = g.v2(p["start"])
    b = g.v2(p["end"])
    L = g.norm(b - a)
    if L < 1e-9 or p["height"] <= 0:
        raise CadError("degenerate", "facade needs length and height")
    spacing = p["spacing"] or 1500 * k
    cols = p["cols"] or max(1, round(L / spacing))
    rows = p["rows"] or max(1, round(p["height"] / spacing))
    if cols < 1 or rows < 1 or cols * rows > 50_000:
        raise CadError("over_budget",
                       f"{cols}x{rows} facade panels is out of budget",
                       hint="check cols/rows/spacing")
    mul = p["mullion"] or 60 * k
    dep = p["depth"] or 120 * k
    pw, ph = L / cols, p["height"] / rows

    parts = []
    for i in range(cols + 1):  # verticals
        parts.append(Manifold.cube((mul, dep, p["height"]), center=True)
                     .translate((i * pw, 0, p["height"] / 2)))
    for j in range(rows + 1):  # horizontals
        parts.append(Manifold.cube((L + mul, dep, mul), center=True)
                     .translate((L / 2, 0, j * ph)))
    mullions = Manifold.batch_boolean(parts, OpType.Add)
    glass = Manifold.cube((L, 25 * k, p["height"]), center=True) \
        .translate((L / 2, 0, p["height"] / 2))

    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

    def place(man):
        return man.rotate((0, 0, ang)).translate((a[0], a[1], p["z"]))

    p_m = dict(p)
    p_m["material"] = p["mullion_material"]
    p_m["tag"] = (p["tag"] + "-mullions") if p["tag"] else None
    mid = _add_solid(doc, place(mullions), p_m, default_layer="facade")
    p_g = dict(p)
    p_g["material"] = p["glass_material"]
    p_g["tag"] = (p["tag"] + "-glass") if p["tag"] else None
    gid = _add_solid(doc, place(glass), p_g, default_layer="facade")
    return {"created": [mid, gid], "cols": cols, "rows": rows,
            "panel": [round(pw, 3), round(ph, 3)]}


# ------------------------------------------------------------------ surface

@op("add_surface",
    doc="Doubly-curved surface slab: z = f(x, y) over a rectangle, given "
        "thickness. The freeform roof/canopy tool — write the surface as "
        "math, e.g. a vault: '6000 - 0.0004*(x-10000)**2 + 0.1*y'. Helpers: "
        "sin/cos/length/smin/smax/clamp/mix.",
    params={
        "expr": P.string(req=True, doc="height field z = f(x, y)"),
        "bounds": P.obj(req=True, doc='{"min": [x, y], "max": [x, y]}'),
        "thickness": P.number(req=True, doc="slab thickness (> 0)"),
        "samples": P.integer(default=48, doc="resolution across the larger "
                                             "side (16-128)"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_surface",
             "expr": "3000 + 1500*sin(x/3000)*cos(y/4000)",
             "bounds": {"min": [0, 0], "max": [20000, 15000]},
             "thickness": 250},
    returns="{created: [id], z_range, volume, bbox}")
def add_surface(doc, p):
    from ..expr import compile_field
    try:
        lo = [float(v) for v in p["bounds"]["min"][:2]]
        hi = [float(v) for v in p["bounds"]["max"][:2]]
        if not all(math.isfinite(v) for v in lo + hi):
            raise ValueError("non-finite bounds")
    except (KeyError, TypeError, ValueError):
        raise CadError("bad_param", 'bounds should be {"min": [x,y], '
                                    '"max": [x,y]} with finite numbers')
    if hi[0] <= lo[0] or hi[1] <= lo[1]:
        raise CadError("bad_param", "bounds max must exceed min")
    if not 16 <= p["samples"] <= 128:
        raise CadError("bad_param", "samples should be 16..128")
    t = p["thickness"]
    if t <= 0:
        raise CadError("bad_param", "thickness must be positive")
    f = compile_field(p["expr"])

    # probe the field to find the z range
    zs = []
    for i in range(13):
        for j in range(13):
            x = lo[0] + (hi[0] - lo[0]) * i / 12
            y = lo[1] + (hi[1] - lo[1]) * j / 12
            try:
                zs.append(f(x, y, 0.0))
            except (ValueError, ZeroDivisionError, OverflowError) as e:
                raise CadError("bad_expr", f"surface failed at ({x}, {y}): {e}")
    zmin, zmax = min(zs), max(zs)

    size = max(hi[0] - lo[0], hi[1] - lo[1])
    el = min(size / p["samples"], t / 2.5)
    pad = el * 2
    bounds3 = [lo[0], lo[1], zmin - t - pad, hi[0], hi[1], zmax + pad]
    cells = ((bounds3[3] - bounds3[0]) / el) * ((bounds3[4] - bounds3[1]) / el) \
        * ((bounds3[5] - bounds3[2]) / el)
    if cells > 12e6:
        raise CadError("over_budget",
                       f"~{cells:.0f} cells exceeds the budget",
                       hint="lower samples, raise thickness, or shrink bounds")

    def field(x, y, z):
        s = f(x, y, 0.0)
        return min(s - z, z - (s - t))  # positive inside the slab

    man = Manifold.level_set(field, bounds3, el)
    if man.is_empty():
        raise CadError("empty_result", "surface produced no geometry")
    sid = _add_solid(doc, man, p, default_layer="roof")
    return {**_solid_result(doc, sid),
            "z_range": [round(zmin, 3), round(zmax, 3)]}
