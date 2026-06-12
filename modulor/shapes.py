"""Bridge between document entities and the geometry kernel (manifold3d).

- closed 2D entities  <->  manifold3d.CrossSection  (robust booleans/offsets)
- solid entities      <->  manifold3d.Manifold      (robust 3D booleans)
- walls are parametric: footprint and 3D body are generated on demand.
"""
from __future__ import annotations

import math

import numpy as np
from manifold3d import CrossSection, FillRule, Manifold, Mesh

from . import geometry as g
from .errors import CadError

EPS = 1e-6


# ---------------------------------------------------------------- 2D: entity -> contours

def spline_points(ent) -> list[list[float]]:
    """Dense polyline of a spline entity."""
    return g.catmull_rom(ent["points"], ent.get("closed", False),
                         ent.get("samples", 12))


def entity_contours(doc, ent) -> list[list[list[float]]]:
    """Closed contours of a 2D entity (for booleans / extrusion / fill)."""
    t = ent["type"]
    if t == "circle":
        return [g.circle_points(ent["center"], ent["radius"], ent.get("segments", 0))]
    if t == "ellipse":
        return [g.ellipse_points(ent["center"], ent["rx"], ent["ry"],
                                 ent.get("rotation", 0.0))]
    if t == "spline":
        if not ent.get("closed"):
            raise CadError("not_closed", "open spline has no area",
                           hint="set closed=true")
        return [g.ensure_ccw(spline_points(ent))]
    if t == "polyline":
        if not ent.get("closed"):
            raise CadError("not_closed", "open polyline has no area",
                           hint="set closed=true or use a region")
        return [g.ensure_ccw(ent["points"])]
    if t in ("region", "hatch"):
        return [c for c in ent["contours"]]
    if t == "room":
        return [g.ensure_ccw(ent["points"])]
    if t == "wall":
        return wall_footprint(doc, ent).to_polygons()
    if t == "instance":
        out = []
        for child in expand_instance(doc, ent):
            try:
                out.extend(entity_contours(doc, child))
            except CadError:
                continue  # open/annotation children carry no area
        if not out:
            raise CadError("not_closed",
                           f"block {ent['block']!r} contains no closed shapes")
        return out
    if t == "arc":
        raise CadError("not_closed", "an arc is an open curve",
                       hint="use a circle, or a closed polyline approximating the shape")
    raise CadError("not_closed", f"entity type {t!r} has no closed contour")


def to_cross_section(doc, ent) -> CrossSection:
    contours = entity_contours(doc, ent)
    return CrossSection(contours, FillRule.Positive)


def cross_section_to_region(cs: CrossSection, layer: str = "0") -> dict:
    polys = cs.to_polygons()
    contours = [[[round(float(x), 6), round(float(y), 6)] for x, y in p] for p in polys]
    return {"contours": contours}


# ---------------------------------------------------------------- walls

def wall_defaults(doc) -> dict:
    """Sensible architectural defaults, scaled to the document units."""
    k = 1.0 / g.unit_scale(doc.units)  # mm -> doc units
    return {
        "height": 3000 * k,
        "door_head": 2100 * k,
        "window_sill": 900 * k,
        "window_head": 2400 * k,
    }


def wall_footprint(doc, ent, with_openings: bool = True) -> CrossSection:
    """Plan-view footprint of a wall; openings cut full gaps through it."""
    contours = g.wall_outline(ent["path"], ent["thickness"])
    cs = CrossSection(contours, FillRule.Positive)
    if with_openings:
        for op in ent.get("openings", []):
            cs = cs - _opening_rect_cs(ent, op)
    if cs.is_empty():
        raise CadError("degenerate", "wall footprint is empty",
                       hint="check path / thickness / opening positions")
    return cs


def _opening_frame(ent, op):
    """Center point + direction of an opening on the wall centerline."""
    pt, d, _ = g.point_along_path(ent["path"], float(op["at"]))
    return pt, d


def _opening_rect_cs(ent, op) -> CrossSection:
    pt, d = _opening_frame(ent, op)
    w = float(op["width"])
    t = ent["thickness"] + EPS * 2 + 0.02 * ent["thickness"]
    n = g.perp(d)
    c = [pt + d * (-w / 2) - n * (t / 2), pt + d * (w / 2) - n * (t / 2),
         pt + d * (w / 2) + n * (t / 2), pt + d * (-w / 2) + n * (t / 2)]
    contour = g.ensure_ccw([[float(x), float(y)] for x, y in c])
    cs = CrossSection([contour], FillRule.Positive)
    if cs.is_empty():
        raise CadError("degenerate", "opening cut rectangle is degenerate")
    return cs


def wall_opening_symbols(doc, ent) -> list[dict]:
    """Plan symbols: window = centerline tick across the gap; door = leaf + swing arc."""
    out = []
    for op in ent.get("openings", []):
        pt, d = _opening_frame(ent, op)
        w = float(op["width"])
        kind = op.get("type", "door")
        if kind == "window":
            a = pt - d * (w / 2)
            b = pt + d * (w / 2)
            out.append({"kind": "line", "points": [[*a], [*b]]})
            n = g.perp(d) * (ent["thickness"] / 2)
            for q in (a, b):
                out.append({"kind": "line", "points": [[*(q - n)], [*(q + n)]]})
        else:  # door: leaf perpendicular at hinge + quarter-circle swing
            hinge = pt - d * (w / 2)
            leaf_dir = g.perp(d)
            leaf_end = hinge + leaf_dir * w
            out.append({"kind": "line", "points": [[*hinge], [*leaf_end]]})
            ang0 = math.degrees(math.atan2(d[1], d[0]))
            ang1 = math.degrees(math.atan2(leaf_dir[1], leaf_dir[0]))
            out.append({"kind": "arc", "center": [*hinge], "radius": w,
                        "start": ang0, "end": ang1})
    return out


def wall_to_manifold(doc, ent) -> Manifold:
    defaults = wall_defaults(doc)
    height = float(ent.get("height") or defaults["height"])
    body = Manifold.extrude(wall_footprint(doc, ent, with_openings=False), height)
    for op in ent.get("openings", []):
        kind = op.get("type", "door")
        if kind == "window":
            sill = float(op.get("sill", defaults["window_sill"]))
            head = float(op.get("head", defaults["window_head"]))
        else:
            sill = float(op.get("sill", 0.0))
            head = float(op.get("head", defaults["door_head"]))
        head = min(head, height)
        if head <= sill:
            raise CadError("degenerate", f"opening head {head} <= sill {sill}")
        cut2d = _opening_rect_cs(ent, op)
        cut = Manifold.extrude(cut2d, head - sill + 2 * EPS).translate((0, 0, sill - EPS))
        body = body - cut
    return body


# ---------------------------------------------------------------- transforms

def transform_entity_data(ent: dict, m2: np.ndarray,
                          m3: np.ndarray | None = None):
    """Apply an affine transform to one entity record in place.

    Used by the transform ops and by block-instance expansion; `ent` may be
    a document entity or a detached copy from a block definition.
    """
    t = ent["type"]
    uniform = g.mat2_is_uniform(m2)
    factor = g.mat2_uniform_factor(m2) if uniform else None
    flips = g.mat2_flips(m2)

    if t == "line":
        ent["start"] = g.apply2(m2, ent["start"])
        ent["end"] = g.apply2(m2, ent["end"])
    elif t in ("polyline", "spline"):
        ent["points"] = g.apply2_many(m2, ent["points"])
        if flips and ent.get("closed"):
            ent["points"] = ent["points"][::-1]
    elif t == "room":
        ent["points"] = g.apply2_many(m2, ent["points"])
        if flips:
            ent["points"] = ent["points"][::-1]
    elif t == "grid":
        lin = m2[:2, :2]
        if not np.allclose(lin, np.eye(2), atol=1e-9):
            raise CadError("bad_type",
                           "grids can only be translated (they define the "
                           "axis system everything else references)")
        ent["xs"] = [x + m2[0, 2] for x in ent["xs"]]
        ent["ys"] = [y + m2[1, 2] for y in ent["ys"]]
    elif t == "circle":
        _need_uniform(t, uniform)
        ent["center"] = g.apply2(m2, ent["center"])
        ent["radius"] = ent["radius"] * factor
    elif t == "ellipse":
        _need_uniform(t, uniform)
        c = ent["center"]
        rot = math.radians(ent.get("rotation", 0.0))
        a_end = [c[0] + ent["rx"] * math.cos(rot),
                 c[1] + ent["rx"] * math.sin(rot)]
        nc = g.apply2(m2, c)
        na = g.apply2(m2, a_end)
        ent["center"] = nc
        ent["rx"] = ent["rx"] * factor
        ent["ry"] = ent["ry"] * factor
        ent["rotation"] = math.degrees(math.atan2(na[1] - nc[1],
                                                  na[0] - nc[0]))
    elif t == "arc":
        _need_uniform(t, uniform)
        c = ent["center"]
        p_start = _arc_point(c, ent["radius"], ent["start_angle"])
        p_end = _arc_point(c, ent["radius"], ent["end_angle"])
        nc = g.apply2(m2, c)
        ns, ne = g.apply2(m2, p_start), g.apply2(m2, p_end)
        a0 = math.degrees(math.atan2(ns[1] - nc[1], ns[0] - nc[0]))
        a1 = math.degrees(math.atan2(ne[1] - nc[1], ne[0] - nc[0]))
        if flips:
            a0, a1 = a1, a0  # keep the arc CCW
        ent["center"] = nc
        ent["radius"] = ent["radius"] * factor
        ent["start_angle"], ent["end_angle"] = a0, a1
    elif t == "region":
        ent["contours"] = [g.apply2_many(m2, c) for c in ent["contours"]]
        if flips:
            ent["contours"] = [c[::-1] for c in ent["contours"]]
    elif t == "hatch":
        _need_uniform(t, uniform)
        ent["contours"] = [g.apply2_many(m2, c) for c in ent["contours"]]
        if flips:
            ent["contours"] = [c[::-1] for c in ent["contours"]]
        ent["spacing"] = ent["spacing"] * factor
        a = math.radians(ent.get("angle", 45.0))
        d = [math.cos(a), math.sin(a)]
        nd = m2[:2, :2] @ np.asarray(d)
        ent["angle"] = math.degrees(math.atan2(nd[1], nd[0]))
    elif t == "text":
        _need_uniform(t, uniform)
        ent["at"] = g.apply2(m2, ent["at"])
        ent["height"] = ent["height"] * factor
        if not flips:
            ent["rotation"] = ent.get("rotation", 0.0) + g.mat2_angle(m2)
        # mirrored text stays readable: position moves, glyphs don't flip
    elif t == "leader":
        _need_uniform(t, uniform)
        ent["points"] = g.apply2_many(m2, ent["points"])
        ent["height"] = ent["height"] * factor
    elif t == "dim":
        _need_uniform(t, uniform)
        ent["p1"] = g.apply2(m2, ent["p1"])
        ent["p2"] = g.apply2(m2, ent["p2"])
        ent["offset"] = ent["offset"] * factor * (-1 if flips else 1)
    elif t == "dim_angular":
        _need_uniform(t, uniform)
        for key in ("center", "p1", "p2"):
            ent[key] = g.apply2(m2, ent[key])
        ent["radius"] = ent["radius"] * factor
        if flips:
            ent["p1"], ent["p2"] = ent["p2"], ent["p1"]  # keep sweep CCW
    elif t == "dim_radial":
        _need_uniform(t, uniform)
        c = ent["center"]
        a = math.radians(ent.get("direction", 45.0))
        edge = [c[0] + ent["radius"] * math.cos(a),
                c[1] + ent["radius"] * math.sin(a)]
        nc = g.apply2(m2, c)
        ne = g.apply2(m2, edge)
        ent["center"] = nc
        ent["radius"] = ent["radius"] * factor
        ent["direction"] = math.degrees(math.atan2(ne[1] - nc[1],
                                                   ne[0] - nc[0]))
    elif t == "wall":
        _need_uniform(t, uniform)
        ent["path"] = g.apply2_many(m2, ent["path"])
        ent["thickness"] = ent["thickness"] * factor
        for opening in ent.get("openings", []):
            opening["at"] = opening["at"] * factor
            opening["width"] = opening["width"] * factor
    elif t == "instance":
        _need_uniform(t, uniform)
        if flips:
            raise CadError("bad_type",
                           "block instances cannot be mirrored",
                           hint="mirror the source entities into a new "
                                "block, or mirror the expanded copy")
        ent["at"] = g.apply2(m2, ent["at"])
        ent["rotation"] = ent.get("rotation", 0.0) + g.mat2_angle(m2)
        ent["scale"] = ent.get("scale", 1.0) * factor
    elif t == "solid":
        man = solid_to_manifold(ent)
        m3 = m3 if m3 is not None else g.mat3_from_mat2(m2)
        man = man.transform(g.mat3_to_manifold(m3))
        if man.is_empty():
            raise CadError("degenerate", "transform collapsed the solid")
        ent["mesh"] = mesh_to_dict(man)
    else:
        raise CadError("bad_type", f"cannot transform entity type {t!r}")


def _need_uniform(t, uniform):
    if not uniform:
        raise CadError("bad_type",
                       f"{t} entities only support uniform scaling",
                       hint="convert to a region first (boolean_2d union) "
                            "for non-uniform scaling")


def _arc_point(c, r, deg):
    a = math.radians(deg)
    return [c[0] + r * math.cos(a), c[1] + r * math.sin(a)]


# ---------------------------------------------------------------- block instances

MAX_INSTANCE_DEPTH = 8


def get_block(doc, name: str) -> dict:
    blk = doc.blocks.get(name)
    if blk is None:
        raise CadError("not_found", f"block {name!r} is not defined",
                       hint=f"defined blocks: {sorted(doc.blocks) or 'none'}")
    return blk


def instance_matrices(doc, ent) -> tuple[np.ndarray, np.ndarray]:
    """(3x3, 4x4) placement transforms of a block instance."""
    blk = get_block(doc, ent["block"])
    bx, by = blk.get("base", [0.0, 0.0])
    s = float(ent.get("scale", 1.0))
    rot = float(ent.get("rotation", 0.0))
    ax, ay = float(ent["at"][0]), float(ent["at"][1])
    m2 = (g.mat2_translate(ax, ay) @ g.mat2_rotate(rot) @
          g.mat2_scale(s, s) @ g.mat2_translate(-bx, -by))
    m3 = (g.mat3_translate(ax, ay, 0.0) @
          g.mat3_rotate_axis([0, 0, 1], rot) @
          g.mat3_scale(s, s, s) @ g.mat3_translate(-bx, -by, 0.0))
    return m2, m3


def expand_instance(doc, ent, depth: int = 0) -> list[dict]:
    """Transformed copies of a block's entities (nested instances expanded)."""
    import copy as _copy
    if depth > MAX_INSTANCE_DEPTH:
        raise CadError("over_budget",
                       f"block nesting deeper than {MAX_INSTANCE_DEPTH}")
    blk = get_block(doc, ent["block"])
    m2, m3 = instance_matrices(doc, ent)
    out = []
    for child in blk["entities"]:
        c = _copy.deepcopy(child)
        transform_entity_data(c, m2, m3)
        if c["type"] == "instance":
            out.extend(expand_instance(doc, c, depth + 1))
        else:
            out.append(c)
    return out


# ---------------------------------------------------------------- 3D: solid <-> mesh

def mesh_to_dict(man: Manifold) -> dict:
    mesh = man.to_mesh()
    verts = np.asarray(mesh.vert_properties, dtype=float)[:, :3]
    tris = np.asarray(mesh.tri_verts, dtype=int)
    return {
        "vertices": [[round(float(v), 5) for v in p] for p in verts],
        "triangles": [[int(i) for i in t] for t in tris],
    }


def solid_to_manifold(ent) -> Manifold:
    m = ent["mesh"]
    vp = np.asarray(m["vertices"], dtype=np.float32)
    tv = np.asarray(m["triangles"], dtype=np.uint32)
    man = Manifold(Mesh(vert_properties=vp, tri_verts=tv))
    if man.is_empty():
        raise CadError("degenerate", "stored mesh is not a valid manifold solid")
    return man


def entity_to_manifold(doc, ent) -> Manifold:
    t = ent["type"]
    if t == "solid":
        return solid_to_manifold(ent)
    if t == "wall":
        return wall_to_manifold(doc, ent)
    if t == "instance":
        mans = [entity_to_manifold(doc, c) for c in expand_instance(doc, ent)
                if c["type"] in ("solid", "wall")]
        if not mans:
            raise CadError("bad_type",
                           f"block {ent['block']!r} contains no 3D bodies",
                           hint="solids and walls can be used in 3D operations")
        man = mans[0]
        for m in mans[1:]:
            man = man + m
        return man
    raise CadError("bad_type", f"entity type {t!r} is not a 3D body",
                   hint="solids and walls can be used in 3D operations")


def collect_meshes(doc, ids) -> list[dict]:
    """Triangle meshes + resolved colors for rendering/export.

    Returns [{id, verts (Nx3 float ndarray), tris (Mx3 int ndarray),
              color (r,g,b 0..1), name}]
    """
    out = []
    for eid in ids:
        ent = doc.entities[eid]
        if ent["type"] == "instance":
            # one mesh entry per 3D child so materials survive
            for k, child in enumerate(expand_instance(doc, ent)):
                if child["type"] not in ("solid", "wall"):
                    continue
                entry = _mesh_entry(doc, f"{eid}.{k}", child)
                if entry:
                    entry["name"] = ent.get("tag") or eid
                    out.append(entry)
            continue
        if ent["type"] not in ("solid", "wall"):
            continue
        entry = _mesh_entry(doc, eid, ent)
        if entry:
            out.append(entry)
    return out


def _mesh_entry(doc, eid: str, ent: dict) -> dict | None:
    man = entity_to_manifold(doc, ent)
    mesh = man.to_mesh()
    verts = np.asarray(mesh.vert_properties, dtype=float)[:, :3]
    tris = np.asarray(mesh.tri_verts, dtype=int)
    if len(tris) == 0:
        return None
    mat = doc.materials.get(ent.get("material") or "default",
                            doc.materials["default"])
    return {
        "id": eid,
        "verts": verts,
        "tris": tris,
        "color": parse_color(mat.get("color", "#9aa0a6")),
        "material": ent.get("material") or "default",
        "name": ent.get("tag") or eid,
    }


# ---------------------------------------------------------------- skinning

def solid_from_rings(rings: list, bottom_tris, top_tris) -> Manifold:
    """Build a watertight solid from a stack of rings (each (n, 3) ndarray,
    same n, CCW seen from ring normal/+travel direction) plus cap
    triangulations (index into a single ring, 0..n-1).
    """
    import numpy as np  # local alias for clarity

    k = len(rings)
    n = len(rings[0])
    if any(len(r) != n for r in rings):
        raise CadError("internal", "all rings must have the same point count")
    verts = np.concatenate([np.asarray(r, dtype=float) for r in rings])
    tris = []
    for a in range(k - 1):
        base0, base1 = a * n, (a + 1) * n
        for i in range(n):
            j = (i + 1) % n
            tris.append([base0 + i, base0 + j, base1 + j])
            tris.append([base0 + i, base1 + j, base1 + i])
    top_base = (k - 1) * n
    for t in np.asarray(bottom_tris, dtype=int):
        tris.append([int(t[0]), int(t[2]), int(t[1])])          # flip: faces -z
    for t in np.asarray(top_tris, dtype=int):
        tris.append([top_base + int(t[0]), top_base + int(t[1]),
                     top_base + int(t[2])])
    tv = np.asarray(tris, dtype=np.uint32)
    man = Manifold(Mesh(vert_properties=verts.astype(np.float32), tri_verts=tv))
    if man.is_empty() or man.volume() < 0:
        flipped = tv[:, [0, 2, 1]].copy()
        man = Manifold(Mesh(vert_properties=verts.astype(np.float32),
                            tri_verts=flipped))
    if man.is_empty():
        raise CadError("degenerate",
                       "could not build a valid solid from the sections",
                       hint="sections may self-intersect or be degenerate; "
                            "try more samples or simpler profiles")
    return man


# ---------------------------------------------------------------- anchors

def entity_anchor(doc, eid: str) -> list[float]:
    """A representative point for labeling an entity (3D; z=0 for flat)."""
    ent = doc.entities[eid]
    t = ent["type"]
    if t == "line":
        a, b = ent["start"], ent["end"]
        return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.0]
    if t in ("polyline", "spline"):
        p = ent["points"][len(ent["points"]) // 2]
        return [p[0], p[1], 0.0]
    if t in ("circle", "arc", "ellipse"):
        return [ent["center"][0], ent["center"][1], 0.0]
    if t == "text":
        return [ent["at"][0], ent["at"][1], 0.0]
    if t == "leader":
        p = ent["points"][0]
        return [p[0], p[1], 0.0]
    if t == "instance":
        return [ent["at"][0], ent["at"][1], 0.0]
    if t == "dim":
        a, b = ent["p1"], ent["p2"]
        return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.0]
    if t == "wall":
        pt, _, _ = g.point_along_path(ent["path"],
                                      g.polyline_length(ent["path"]) / 2)
        return [float(pt[0]), float(pt[1]), 0.0]
    box = entity_bbox(doc, eid)
    if box.empty:
        return [0.0, 0.0, 0.0]
    c = box.center()
    return [float(c[0]), float(c[1]), float(c[2])]


def entity_label(doc, eid: str) -> str:
    tag = doc.entities[eid].get("tag")
    return f"{eid}:{tag}" if tag else eid


# ---------------------------------------------------------------- bbox

def entity_bbox(doc, eid: str) -> g.BBox:
    return ent_bbox(doc, doc.entities[eid])


def ent_bbox(doc, ent: dict) -> g.BBox:
    t = ent["type"]
    box = g.BBox()
    if t == "line":
        box.add_many([ent["start"], ent["end"]])
    elif t == "polyline":
        box.add_many(ent["points"])
    elif t == "spline":
        box.add_many(spline_points(ent))
    elif t == "circle":
        c, r = ent["center"], ent["radius"]
        box.add([c[0] - r, c[1] - r])
        box.add([c[0] + r, c[1] + r])
    elif t == "ellipse":
        box.add_many(g.ellipse_points(ent["center"], ent["rx"], ent["ry"],
                                      ent.get("rotation", 0.0)))
    elif t == "hatch":
        for c in ent["contours"]:
            box.add_many(c)
    elif t == "leader":
        box.add_many(ent["points"])
        h = ent.get("height", 1.0)
        tip = ent["points"][-1]
        box.add([tip[0] + h * 0.6 * len(ent.get("text", "")), tip[1] + h])
    elif t == "instance":
        for child in expand_instance(doc, ent):
            box.merge(ent_bbox(doc, child))
    elif t == "arc":
        box.add_many(g.arc_points(ent["center"], ent["radius"],
                                  ent["start_angle"], ent["end_angle"], 32))
    elif t == "region":
        for c in ent["contours"]:
            box.add_many(c)
    elif t == "text":
        box.add(ent["at"])
        h = ent.get("height", 1.0)
        box.add([ent["at"][0] + h * 0.6 * len(ent["text"]), ent["at"][1] + h])
    elif t == "dim":
        box.add_many([ent["p1"], ent["p2"]])
    elif t == "dim_angular":
        c, r = ent["center"], ent["radius"] * 1.3
        box.add([c[0] - r, c[1] - r])
        box.add([c[0] + r, c[1] + r])
    elif t == "dim_radial":
        c, r = ent["center"], ent["radius"] * 1.5
        box.add([c[0] - r, c[1] - r])
        box.add([c[0] + r, c[1] + r])
    elif t == "wall":
        for c in wall_footprint(doc, ent, with_openings=False).to_polygons():
            box.add_many(c)
    elif t == "room":
        box.add_many(ent["points"])
    elif t == "grid":
        xs, ys = ent["xs"], ent["ys"]
        pad = max(xs[-1] - xs[0], ys[-1] - ys[0]) * 0.08
        box.add([xs[0] - pad, ys[0] - pad])
        box.add([xs[-1] + pad, ys[-1] + pad])
    elif t == "solid":
        v = np.asarray(ent["mesh"]["vertices"], dtype=float)
        if len(v):
            box.add(v.min(axis=0))
            box.add(v.max(axis=0))
    return box


def doc_bbox(doc, ids=None) -> g.BBox:
    box = g.BBox()
    for eid in (ids if ids is not None else doc.entities.keys()):
        box.merge(entity_bbox(doc, eid))
    return box


# ---------------------------------------------------------------- colors

def parse_color(c) -> tuple[float, float, float]:
    """'#rrggbb' or [r,g,b] 0..255 or 0..1 -> floats 0..1."""
    if isinstance(c, str):
        s = c.lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        try:
            return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        except ValueError:
            raise CadError("bad_param", f"cannot parse color {c!r}",
                           hint="use '#rrggbb'")
    v = [float(x) for x in c]
    if max(v) > 1.0:
        v = [x / 255.0 for x in v]
    return (v[0], v[1], v[2])


def color_hex(rgb) -> str:
    return "#" + "".join(f"{int(round(max(0, min(1, v)) * 255)):02x}" for v in rgb)
