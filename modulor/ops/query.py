"""Measurement and validation ops — the feedback loop agents rely on."""
from __future__ import annotations

from .. import geometry as g
from .. import shapes
from ..errors import CadError
from . import P, op


@op("measure",
    doc="Measure geometry: distance between two points, or length / area / "
        "volume / bbox of selected entities.",
    params={
        "kind": P.enum(["distance", "length", "area", "volume", "bbox"],
                       req=True, doc="what to measure"),
        "p1": P.point3(doc="distance: first point"),
        "p2": P.point3(doc="distance: second point"),
        "select": P.select(doc="length/area/volume/bbox: target entities"),
    },
    example={"op": "measure", "kind": "area", "select": "e4"},
    returns="{value} or {bbox, size, center}", effects="none")
def measure(doc, p):
    kind = p["kind"]
    if kind == "distance":
        if p["p1"] is None or p["p2"] is None:
            raise CadError("missing_param", "distance needs p1 and p2")
        d = g.norm(g.v3(p["p2"]) - g.v3(p["p1"]))
        return {"value": round(d, 6), "units": doc.units}

    ids = doc.select(p["select"] if p["select"] is not None else "all")
    if not ids:
        raise CadError("empty_selection", "selector matched nothing")

    if kind == "bbox":
        box = shapes.doc_bbox(doc, ids)
        if box.empty:
            return {"bbox": None}
        return {"bbox": box.as_dict(),
                "size": [round(float(v), 6) for v in box.size()],
                "center": [round(float(v), 6) for v in box.center()]}

    if kind == "length":
        total = 0.0
        for eid in ids:
            ent = doc.entities[eid]
            t = ent["type"]
            if t == "line":
                total += g.norm(g.v2(ent["end"]) - g.v2(ent["start"]))
            elif t == "polyline":
                total += g.polyline_length(ent["points"], ent.get("closed", False))
            elif t == "spline":
                total += g.polyline_length(shapes.spline_points(ent),
                                           ent.get("closed", False))
            elif t == "circle":
                total += g.TAU * ent["radius"]
            elif t == "ellipse":
                total += g.polyline_length(
                    g.ellipse_points(ent["center"], ent["rx"], ent["ry"],
                                     ent.get("rotation", 0.0)), closed=True)
            elif t == "arc":
                sweep = (ent["end_angle"] - ent["start_angle"]) % 360.0 or 360.0
                total += g.TAU * ent["radius"] * sweep / 360.0
            elif t == "wall":
                total += g.polyline_length(ent["path"])
            elif t == "region":
                for c in ent["contours"]:
                    total += g.polyline_length(c, closed=True)
        return {"value": round(total, 6), "units": doc.units}

    if kind == "area":
        total = 0.0
        for eid in ids:
            ent = doc.entities[eid]
            if ent["type"] in ("circle", "ellipse", "polyline", "spline",
                               "region", "hatch", "wall", "room"):
                total += shapes.to_cross_section(doc, ent).area()
            elif ent["type"] == "instance":
                try:
                    total += shapes.to_cross_section(doc, ent).area()
                except CadError:
                    pass  # blocks without closed shapes contribute nothing
        return {"value": round(total, 6), "units": f"{doc.units}^2"}

    # volume
    total = 0.0
    for eid in ids:
        ent = doc.entities[eid]
        if ent["type"] in ("solid", "wall"):
            total += shapes.entity_to_manifold(doc, ent).volume()
        elif ent["type"] == "instance":
            try:
                total += shapes.entity_to_manifold(doc, ent).volume()
            except CadError:
                pass  # blocks without 3D bodies contribute nothing
    return {"value": round(total, 6), "units": f"{doc.units}^3"}


@op("find",
    doc="Spatial query: which entities are at/near a point, or inside a "
        "box? Results are sorted by distance. The fastest way to rebuild "
        "your mental map of a drawing.",
    params={
        "at": P.point3(doc="query point [x, y] or [x, y, z]"),
        "radius": P.number(doc="with 'at': only entities within this distance"),
        "bbox": P.obj(doc='{"min": [x,y(,z)], "max": [x,y(,z)]}: only '
                          "entities whose bounds overlap this box"),
        "select": P.select(default="all",
                           doc="restrict the search to these entities"),
        "limit": P.integer(default=10, doc="max results returned"),
    },
    example={"op": "find", "at": [2500, 1200], "radius": 500},
    returns="{found: [{id, type, layer, tag?, distance, bbox}]}",
    effects="none")
def find(doc, p):
    if p["at"] is None and p["bbox"] is None:
        raise CadError("missing_param", "find needs 'at' or 'bbox'")
    ids = doc.select(p["select"])

    qmin = qmax = None
    if p["bbox"] is not None:
        try:
            qmin = [float(v) for v in p["bbox"]["min"]] + [0.0] * 3
            qmax = [float(v) for v in p["bbox"]["max"]] + [0.0] * 3
        except (KeyError, TypeError, ValueError):
            raise CadError("bad_param", "bbox should be "
                           '{"min": [x,y(,z)], "max": [x,y(,z)]}')

    rows = []
    for eid in ids:
        box = shapes.entity_bbox(doc, eid)
        if box.empty:
            continue
        if qmin is not None:
            n = min(len(p["bbox"]["min"]), 3)
            if any(box.max[i] < qmin[i] or box.min[i] > qmax[i]
                   for i in range(n)):
                continue
        dist = 0.0
        if p["at"] is not None:
            q = g.v3(p["at"])
            clamped = [min(max(q[i], box.min[i]), box.max[i]) for i in range(3)]
            dist = g.norm(q - clamped)
            if p["radius"] is not None and dist > p["radius"]:
                continue
        ent = doc.entities[eid]
        row = {"id": eid, "type": ent["type"], "layer": ent["layer"],
               "distance": round(dist, 6), "bbox": box.as_dict()}
        if ent.get("tag"):
            row["tag"] = ent["tag"]
        rows.append(row)
    rows.sort(key=lambda r: r["distance"])
    return {"count": len(rows), "found": rows[:p["limit"]]}


@op("validate",
    doc="Check the document for problems: degenerate entities, broken meshes, "
        "openings outside their walls, references to missing materials.",
    params={},
    example={"op": "validate"},
    returns="{valid, problems: [{id, code, message}]}", effects="none")
def validate(doc, p):
    problems = []

    def add(eid, code, message):
        problems.append({"id": eid, "code": code, "message": message})

    for eid, ent in doc.entities.items():
        t = ent["type"]
        try:
            if t == "line":
                if g.norm(g.v2(ent["end"]) - g.v2(ent["start"])) < 1e-9:
                    add(eid, "degenerate", "zero-length line")
            elif t == "polyline":
                if len(ent["points"]) < 2:
                    add(eid, "degenerate", "polyline with < 2 points")
                elif ent.get("closed") and abs(g.polygon_area(ent["points"])) < 1e-12:
                    add(eid, "degenerate", "closed polyline with zero area")
            elif t in ("circle", "arc"):
                if ent["radius"] <= 0:
                    add(eid, "degenerate", "non-positive radius")
            elif t == "ellipse":
                if ent["rx"] <= 0 or ent["ry"] <= 0:
                    add(eid, "degenerate", "non-positive semi-axis")
            elif t == "hatch":
                if ent["spacing"] <= 0:
                    add(eid, "degenerate", "non-positive hatch spacing")
                if not ent.get("contours"):
                    add(eid, "degenerate", "hatch without contours")
            elif t == "leader":
                if len(ent["points"]) < 2:
                    add(eid, "degenerate", "leader with < 2 points")
            elif t == "instance":
                shapes.expand_instance(doc, ent)  # raises with details
            elif t == "wall":
                length = g.polyline_length(ent["path"])
                shapes.wall_footprint(doc, ent)
                for i, opening in enumerate(ent.get("openings", [])):
                    half = opening["width"] / 2
                    if opening["at"] - half < -1e-9 or opening["at"] + half > length + 1e-9:
                        add(eid, "opening_overflow",
                            f"opening {i} extends past the wall ends")
                shapes.wall_to_manifold(doc, ent)
            elif t == "solid":
                man = shapes.solid_to_manifold(ent)
                if man.volume() <= 0:
                    add(eid, "degenerate", "solid with non-positive volume")
            if ent.get("material") and ent["material"] not in doc.materials:
                add(eid, "missing_material",
                    f"references undefined material {ent['material']!r}")
            if ent.get("layer") not in doc.layers:
                add(eid, "missing_layer",
                    f"references undefined layer {ent.get('layer')!r}")
        except CadError as e:
            add(eid, e.code, e.message)
    return {"valid": not problems, "problems": problems}
