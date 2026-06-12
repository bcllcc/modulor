"""2D drafting ops: primitives, walls, dimensions, text, booleans, offsets."""
from __future__ import annotations


from manifold3d import CrossSection, FillRule, JoinType

from .. import geometry as g
from .. import shapes
from ..errors import CadError
from . import P, op


@op("add_line",
    doc="Add a straight line segment.",
    params={
        "start": P.point2(req=True),
        "end": P.point2(req=True),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_line", "start": [0, 0], "end": [1000, 0]},
    returns="{created: [id]}")
def add_line(doc, p):
    if g.norm(g.v2(p["end"]) - g.v2(p["start"])) < 1e-12:
        raise CadError("degenerate", "line start and end coincide")
    eid = doc.add_entity("line", {"start": p["start"], "end": p["end"]},
                         layer=p["layer"] or "0", tag=p["tag"])
    return {"created": [eid]}


@op("add_polyline",
    doc="Add a polyline (open or closed). Closed polylines bound an area and "
        "can be extruded or used in 2D booleans.",
    params={
        "points": P.points(req=True),
        "closed": P.boolean(default=False,
                            doc="close the loop (bounds an area)"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_polyline",
             "points": [[0, 0], [500, 0], [500, 300], [0, 300]], "closed": True},
    returns="{created: [id]}")
def add_polyline(doc, p):
    pts = p["points"]
    if len(pts) < 2:
        raise CadError("degenerate", "polyline needs at least 2 points")
    if p["closed"] and len(pts) < 3:
        raise CadError("degenerate", "closed polyline needs at least 3 points")
    if p["closed"] and g.norm(g.v2(pts[0]) - g.v2(pts[-1])) < 1e-9:
        pts = pts[:-1]  # drop duplicated closing point
    eid = doc.add_entity("polyline", {"points": pts, "closed": p["closed"]},
                         layer=p["layer"] or "0", tag=p["tag"])
    return {"created": [eid]}


@op("add_rect",
    doc="Add an axis-aligned rectangle (a closed polyline), optionally rotated.",
    params={
        "at": P.point2(req=True, doc="anchor point [x, y]"),
        "width": P.number(req=True, doc="size along x (> 0)"),
        "height": P.number(req=True, doc="size along y (> 0)"),
        "anchor": P.enum(["corner", "center"], default="corner",
                         doc="'at' is the lower-left corner or the center"),
        "rotation": P.number(default=0.0, doc="degrees CCW about the anchor"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_rect", "at": [0, 0], "width": 400, "height": 250},
    returns="{created: [id]}")
def add_rect(doc, p):
    w, h = p["width"], p["height"]
    if w <= 0 or h <= 0:
        raise CadError("degenerate", "rectangle needs positive width and height")
    x, y = p["at"]
    if p["anchor"] == "center":
        x, y = x - w / 2, y - h / 2
    pts = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    if p["rotation"]:
        m = g.mat2_rotate(p["rotation"], center=p["at"])
        pts = g.apply2_many(m, pts)
    eid = doc.add_entity("polyline", {"points": pts, "closed": True},
                         layer=p["layer"] or "0", tag=p["tag"])
    return {"created": [eid]}


@op("add_spline",
    doc="Add a smooth curve through the given points (centripetal "
        "Catmull-Rom). Closed splines bound an area: they can be extruded, "
        "lofted, swept and used in 2D booleans like any closed shape.",
    params={
        "points": P.points(req=True, doc="points the curve passes through"),
        "closed": P.boolean(default=False,
                            doc="close the loop (bounds an area)"),
        "samples": P.integer(default=12, doc="curve segments between points "
                                             "(quality vs size)"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_spline", "closed": True,
             "points": [[0, 0], [4000, 1500], [7000, 0], [5000, -2500]]},
    returns="{created: [id], length}")
def add_spline(doc, p):
    if len(p["points"]) < 3:
        raise CadError("degenerate", "spline needs at least 3 points")
    if p["samples"] < 2 or p["samples"] > 64:
        raise CadError("bad_param", "samples should be between 2 and 64")
    eid = doc.add_entity("spline", {"points": p["points"], "closed": p["closed"],
                                    "samples": p["samples"]},
                         layer=p["layer"] or "0", tag=p["tag"])
    pts = shapes.spline_points(doc.entities[eid])
    return {"created": [eid],
            "length": round(g.polyline_length(pts, p["closed"]), 6)}


@op("add_circle",
    doc="Add a circle.",
    params={
        "center": P.point2(req=True),
        "radius": P.number(req=True, doc="radius (> 0)"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_circle", "center": [100, 100], "radius": 50},
    returns="{created: [id]}")
def add_circle(doc, p):
    if p["radius"] <= 0:
        raise CadError("degenerate", "circle needs a positive radius")
    eid = doc.add_entity("circle", {"center": p["center"], "radius": p["radius"]},
                         layer=p["layer"] or "0", tag=p["tag"])
    return {"created": [eid]}


@op("add_arc",
    doc="Add a circular arc, CCW from start_angle to end_angle (degrees from +X).",
    params={
        "center": P.point2(req=True),
        "radius": P.number(req=True, doc="radius (> 0)"),
        "start_angle": P.number(req=True, doc="degrees"),
        "end_angle": P.number(req=True, doc="degrees"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_arc", "center": [0, 0], "radius": 80,
             "start_angle": 0, "end_angle": 90},
    returns="{created: [id]}")
def add_arc(doc, p):
    if p["radius"] <= 0:
        raise CadError("degenerate", "arc needs a positive radius")
    eid = doc.add_entity("arc", {"center": p["center"], "radius": p["radius"],
                                 "start_angle": p["start_angle"],
                                 "end_angle": p["end_angle"]},
                         layer=p["layer"] or "0", tag=p["tag"])
    return {"created": [eid]}


@op("add_text",
    doc="Add a text label.",
    params={
        "at": P.point2(req=True, doc="baseline-left anchor"),
        "text": P.string(req=True, doc="the label text"),
        "height": P.number(default=None, doc="cap height in doc units "
                                             "(default: 250mm equivalent)"),
        "rotation": P.number(default=0.0, doc="degrees CCW"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_text", "at": [200, 150], "text": "KITCHEN", "height": 200},
    returns="{created: [id]}")
def add_text(doc, p):
    height = p["height"]
    if height is None:
        height = 250.0 / g.unit_scale(doc.units)
    eid = doc.add_entity("text", {"at": p["at"], "text": p["text"],
                                  "height": height, "rotation": p["rotation"]},
                         layer=p["layer"] or "0", tag=p["tag"])
    return {"created": [eid]}


@op("add_dim",
    doc="Add an aligned linear dimension between two points. The measured "
        "distance is rendered automatically; offset places the dimension line "
        "to the left (+) or right (-) of the p1->p2 direction.",
    params={
        "p1": P.point2(req=True),
        "p2": P.point2(req=True),
        "offset": P.number(default=None, doc="distance from measured points "
                                             "(default: 500mm equivalent)"),
        "text": P.string(doc="override the measured value"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_dim", "p1": [0, 0], "p2": [4000, 0], "offset": -600},
    returns="{created: [id], value}")
def add_dim(doc, p):
    d = g.norm(g.v2(p["p2"]) - g.v2(p["p1"]))
    if d < 1e-12:
        raise CadError("degenerate", "dimension points coincide")
    offset = p["offset"]
    if offset is None:
        offset = 500.0 / g.unit_scale(doc.units)
    data = {"p1": p["p1"], "p2": p["p2"], "offset": offset}
    if p["text"]:
        data["text"] = p["text"]
    eid = doc.add_entity("dim", data, layer=p["layer"] or "dims", tag=p["tag"])
    return {"created": [eid], "value": round(d, 6)}


@op("add_wall",
    doc="Add a wall along a centerline path. Walls render as double lines in "
        "plan and extrude to 3D automatically. Openings (doors/windows) are "
        "cut with add_opening.",
    params={
        "path": P.points(req=True, doc="centerline [[x,y], ...]"),
        "thickness": P.number(req=True, doc="wall thickness (> 0)"),
        "height": P.number(doc="3D height (default: 3000mm equivalent)"),
        "smooth": P.boolean(default=False,
                            doc="run a Catmull-Rom spline through the path "
                                "points: curved walls"),
        "layer": P.layer(),
        "tag": P.tag(),
        "material": P.string(doc="material for 3D rendering/export"),
    },
    example={"op": "add_wall", "path": [[0, 0], [6000, 0], [6000, 4000]],
             "thickness": 200, "tag": "exterior"},
    returns="{created: [id], length}")
def add_wall(doc, p):
    if len(p["path"]) < 2:
        raise CadError("degenerate", "wall path needs at least 2 points")
    if p["thickness"] <= 0:
        raise CadError("degenerate", "wall thickness must be positive")
    path = p["path"]
    if p["smooth"]:
        if len(path) < 3:
            raise CadError("degenerate", "a smooth wall needs at least 3 points")
        closed = g.path_is_closed(path)
        path = g.catmull_rom(path, closed=closed, samples_per_seg=10)
        if closed:
            path = path + [path[0]]  # keep the closed-ring convention
    data = {"path": path, "thickness": p["thickness"], "openings": []}
    if p["height"]:
        data["height"] = p["height"]
    if p["material"]:
        data["material"] = p["material"]
    # validate-before-mutate: a failing wall must not enter the document
    try:
        shapes.wall_footprint(doc, data)
    except CadError:
        raise
    except Exception as e:
        raise CadError("degenerate",
                       f"wall geometry is not constructible: {e}",
                       hint="check path, thickness and scale")
    eid = doc.add_entity("wall", data, layer=p["layer"] or "walls", tag=p["tag"])
    return {"created": [eid], "length": round(g.polyline_length(path), 6)}


@op("add_opening",
    doc="Cut a door or window into a wall. Position is the distance along the "
        "wall centerline to the opening center.",
    params={
        "wall": P.select(req=True, doc="the wall: id, tag or selector "
                                       "(must match exactly one wall)"),
        "along": P.number(req=True,
                          doc="distance along the centerline to the "
                              "opening center"),
        "width": P.number(req=True, doc="opening width (> 0)"),
        "type": P.enum(["door", "window"], default="door",
                       doc="drawing symbol + default sill/head"),
        "sill": P.number(doc="bottom height (default: door 0, window 900mm eq.)"),
        "head": P.number(doc="top height (default: door 2100, window 2400mm eq.)"),
    },
    example={"op": "add_opening", "wall": "e1", "along": 1200,
             "width": 900, "type": "door"},
    returns="{modified: [wall id], openings}")
def add_opening(doc, p):
    ids = [eid for eid in doc.select(p["wall"])
           if doc.entities[eid]["type"] == "wall"]
    if len(ids) != 1:
        raise CadError("bad_target",
                       f"selector matched {len(ids)} walls, need exactly 1",
                       hint="give the wall a unique tag or use its id")
    ent = doc.entities[ids[0]]
    length = g.polyline_length(ent["path"])
    if not (0 < p["along"] < length):
        raise CadError("bad_param",
                       f"opening center {p['along']} outside wall length "
                       f"{round(length, 3)}")
    if p["width"] <= 0:
        raise CadError("degenerate", "opening width must be positive")
    opening = {"at": p["along"], "width": p["width"], "type": p["type"]}
    if p["sill"] is not None:
        opening["sill"] = p["sill"]
    if p["head"] is not None:
        opening["head"] = p["head"]
    # validate the cut on a copy before committing it to the wall
    trial = dict(ent)
    trial["openings"] = list(ent.get("openings", [])) + [opening]
    try:
        shapes.wall_footprint(doc, trial)
        shapes.wall_to_manifold(doc, trial)
    except CadError:
        raise
    except Exception as e:
        raise CadError("degenerate", f"opening is not constructible: {e}")
    ent.setdefault("openings", []).append(opening)
    return {"modified": [ids[0]], "openings": len(ent["openings"])}


@op("fillet",
    doc="Round the corners of polylines with arcs of the given radius "
        "(in place). Radius is clamped per corner when segments are short.",
    params={
        "select": P.select(req=True, doc="polyline entities (open or closed)"),
        "radius": P.number(req=True, doc="corner arc radius (> 0)"),
    },
    example={"op": "fillet", "select": "e2", "radius": 50},
    returns="{modified: [ids], corners, clamped}")
def fillet(doc, p):
    return _round_op(doc, p, chamfer=False)


@op("chamfer",
    doc="Cut the corners of polylines with straight bevels at the given "
        "setback distance (in place).",
    params={
        "select": P.select(req=True, doc="polyline entities (open or closed)"),
        "distance": P.number(req=True, doc="setback from each corner"),
    },
    example={"op": "chamfer", "select": "e2", "distance": 30},
    returns="{modified: [ids], corners, clamped}")
def chamfer(doc, p):
    return _round_op(doc, p, chamfer=True)


def _round_op(doc, p, chamfer: bool):
    size = p["distance" if chamfer else "radius"]
    if size <= 0:
        raise CadError("bad_param", "radius/distance must be positive")
    ids = [eid for eid in doc.select(p["select"])
           if doc.entities[eid]["type"] == "polyline"]
    if not ids:
        raise CadError("empty_selection", "no polylines in selection",
                       hint="fillet/chamfer work on polyline entities "
                            "(add_rect makes one)")
    done = clamped = 0
    for eid in ids:
        ent = doc.entities[eid]
        pts, d, c = g.round_corners(ent["points"], bool(ent.get("closed")),
                                    size, chamfer=chamfer)
        ent["points"] = pts
        done += d
        clamped += c
    return {"modified": ids, "corners": done, "clamped": clamped}


@op("add_dim_angular",
    doc="Angular dimension: measures the CCW angle at `center` from the ray "
        "toward p1 to the ray toward p2, drawn as an arc at `radius`.",
    params={
        "center": P.point2(req=True),
        "p1": P.point2(req=True, doc="point on the first ray"),
        "p2": P.point2(req=True, doc="point on the second ray"),
        "radius": P.number(doc="arc placement radius (default: mean of the "
                               "two point distances)"),
        "text": P.string(doc="override the measured value"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_dim_angular", "center": [0, 0], "p1": [500, 0],
             "p2": [400, 400]},
    returns="{created: [id], value}")
def add_dim_angular(doc, p):
    import math as _m
    c = g.v2(p["center"])
    v1 = g.v2(p["p1"]) - c
    v2 = g.v2(p["p2"]) - c
    if g.norm(v1) < 1e-9 or g.norm(v2) < 1e-9:
        raise CadError("degenerate", "rays have zero length")
    a1 = _m.degrees(_m.atan2(v1[1], v1[0]))
    a2 = _m.degrees(_m.atan2(v2[1], v2[0]))
    sweep = (a2 - a1) % 360.0
    radius = p["radius"] or (g.norm(v1) + g.norm(v2)) / 2
    data = {"center": p["center"], "p1": p["p1"], "p2": p["p2"],
            "radius": radius}
    if p["text"]:
        data["text"] = p["text"]
    eid = doc.add_entity("dim_angular", data, layer=p["layer"] or "dims",
                         tag=p["tag"])
    return {"created": [eid], "value": round(sweep, 6)}


@op("add_dim_radial",
    doc="Radius dimension on a circle or arc: a leader at `angle` with the "
        "text 'R<value>'.",
    params={
        "of": P.select(req=True, doc="one circle or arc entity"),
        "direction": P.number(default=45.0, doc="leader direction, degrees"),
        "text": P.string(doc="override the measured value"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_dim_radial", "of": "e4", "direction": 30},
    returns="{created: [id], value}")
def add_dim_radial(doc, p):
    ids = [eid for eid in doc.select(p["of"])
           if doc.entities[eid]["type"] in ("circle", "arc")]
    if len(ids) != 1:
        raise CadError("bad_target",
                       f"selector matched {len(ids)} circles/arcs, need 1")
    src = doc.entities[ids[0]]
    data = {"center": src["center"], "radius": src["radius"],
            "direction": p["direction"]}
    if p["text"]:
        data["text"] = p["text"]
    eid = doc.add_entity("dim_radial", data, layer=p["layer"] or "dims",
                         tag=p["tag"])
    return {"created": [eid], "value": round(src["radius"], 6)}


_JOIN = {"round": JoinType.Round, "miter": JoinType.Miter, "square": JoinType.Square}


@op("offset",
    doc="Offset closed shapes outward (+) or inward (-) by a distance. "
        "Produces a region; the source is kept.",
    params={
        "select": P.select(req=True, doc="closed shapes (circle/closed "
                                         "polyline/region/wall footprint)"),
        "delta": P.number(req=True, doc="+ grows, - shrinks"),
        "join": P.enum(["round", "miter", "square"], default="miter",
                       doc="corner treatment of the offset contour"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "offset", "select": "e2", "delta": 150},
    returns="{created: [id]}")
def offset(doc, p):
    ids = doc.select(p["select"])
    if not ids:
        raise CadError("empty_selection", "nothing selected")
    created = []
    for eid in ids:
        ent = doc.entities[eid]
        cs = shapes.to_cross_section(doc, ent)
        out = cs.offset(p["delta"], _JOIN[p["join"]])
        if out.is_empty():
            raise CadError("empty_result",
                           f"offsetting {eid} by {p['delta']} left nothing",
                           hint="inward offset larger than the shape?")
        data = shapes.cross_section_to_region(out)
        created.append(doc.add_entity("region", data,
                                      layer=p["layer"] or ent["layer"],
                                      tag=p["tag"]))
    return {"created": created}


@op("boolean_2d",
    doc="2D boolean between closed shapes. Inputs are consumed unless "
        "keep=true; the result is one region entity.",
    params={
        "kind": P.enum(["union", "difference", "intersect", "xor"],
               req=True, doc="boolean operation"),
        "a": P.select(req=True, doc="first operand(s), unioned together"),
        "b": P.select(doc="second operand(s); not needed for plain union"),
        "keep": P.boolean(default=False, doc="keep input entities"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "boolean_2d", "kind": "difference", "a": "e1", "b": ["e2", "e3"]},
    returns="{created: [id], area}")
def boolean_2d(doc, p):
    a_ids = doc.select(p["a"])
    if not a_ids:
        raise CadError("empty_selection", "selector 'a' matched nothing")
    b_ids = doc.select(p["b"]) if p["b"] is not None else []
    overlap = set(a_ids) & set(b_ids)
    if overlap:
        raise CadError("bad_target", f"entities {sorted(overlap)} are in both "
                                        "'a' and 'b'")
    cs_a = _union_cs(doc, a_ids)
    if b_ids:
        cs_b = _union_cs(doc, b_ids)
        if p["kind"] == "union":
            result = cs_a + cs_b
        elif p["kind"] == "difference":
            result = cs_a - cs_b
        elif p["kind"] == "intersect":
            result = cs_a ^ cs_b
        else:
            result = (cs_a + cs_b) - (cs_a ^ cs_b)
    else:
        if p["kind"] != "union":
            raise CadError("missing_param", f"{p['kind']} needs operand 'b'")
        result = cs_a
    if result.is_empty():
        raise CadError("empty_result", "boolean produced empty geometry",
                       hint="check that the shapes actually overlap")
    layer = p["layer"] or doc.entities[a_ids[0]]["layer"]
    if not p["keep"]:
        doc.delete_entities(a_ids + b_ids)
    data = shapes.cross_section_to_region(result)
    eid = doc.add_entity("region", data, layer=layer, tag=p["tag"])
    return {"created": [eid], "area": round(result.area(), 6)}


def _union_cs(doc, ids) -> CrossSection:
    contours = []
    for eid in ids:
        contours.extend(shapes.entity_contours(doc, doc.entities[eid]))
    return CrossSection(contours, FillRule.Positive)
