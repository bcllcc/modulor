"""3D modeling ops: primitives, extrude/revolve, booleans, slice/project,
and the freeform layer (loft / sweep / deform / implicit surfaces / smooth)."""
from __future__ import annotations

import math

import numpy as np
from manifold3d import CrossSection, FillRule, Manifold, OpType, triangulate

from .. import geometry as g
from .. import shapes
from ..errors import CadError
from . import P, op


def _check_segments(p, cap: int = 512):
    s = p.get("segments")
    if s is not None and (s < 0 or s > cap):
        raise CadError("over_budget",
                       f"segments = {s} exceeds the budget of {cap}",
                       hint="0 picks a sensible automatic count")


def _add_solid(doc, man: Manifold, p, default_layer="model") -> str:
    if man.is_empty():
        raise CadError("empty_result", "operation produced an empty solid")
    data = {"mesh": shapes.mesh_to_dict(man)}
    mat = p.get("material")
    if mat:
        if mat not in doc.materials:
            raise CadError("not_found", f"material {mat!r} not defined",
                           hint="create it first with add_material")
        data["material"] = mat
    return doc.add_entity("solid", data, layer=p.get("layer") or default_layer,
                          tag=p.get("tag"))


def _solid_result(doc, eid: str) -> dict:
    ent = doc.entities[eid]
    man = shapes.solid_to_manifold(ent)
    return {"created": [eid],
            "volume": round(man.volume(), 6),
            "bbox": shapes.entity_bbox(doc, eid).as_dict()}


@op("add_box",
    doc="Add an axis-aligned box solid.",
    params={
        "at": P.point3(default=[0.0, 0.0, 0.0], doc="anchor point"),
        "size": P.point3(req=True, doc="[sx, sy, sz]"),
        "anchor": P.enum(["corner", "center"], default="corner",
                         doc="'at' is the min corner or the 3D center"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_box", "at": [0, 0, 0], "size": [2000, 1000, 750]},
    returns="{created: [id], volume, bbox}")
def add_box(doc, p):
    sx, sy, sz = p["size"]
    if min(sx, sy, sz) <= 0:
        raise CadError("degenerate", "box needs positive size in all axes")
    man = Manifold.cube((sx, sy, sz), center=(p["anchor"] == "center"))
    man = man.translate(tuple(p["at"]))
    return _solid_result(doc, _add_solid(doc, man, p))


@op("add_cylinder",
    doc="Add a cylinder (or cone, with radius_top) standing on its base.",
    params={
        "at": P.point3(default=[0.0, 0.0, 0.0], doc="center of the base circle"),
        "radius": P.number(req=True, doc="base radius"),
        "height": P.number(req=True, doc="height (> 0)"),
        "radius_top": P.number(doc="top radius; 0 makes a cone (default: radius)"),
        "segments": P.integer(default=0, doc="0 = automatic"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_cylinder", "at": [500, 500, 0], "radius": 150,
             "height": 2800},
    returns="{created: [id], volume, bbox}")
def add_cylinder(doc, p):
    _check_segments(p)
    if p["radius"] <= 0 or p["height"] <= 0:
        raise CadError("degenerate", "cylinder needs positive radius and height")
    r_top = p["radius"] if p["radius_top"] is None else p["radius_top"]
    if r_top < 0:
        raise CadError("degenerate", "radius_top cannot be negative")
    man = Manifold.cylinder(p["height"], p["radius"], r_top, p["segments"])
    man = man.translate(tuple(p["at"]))
    return _solid_result(doc, _add_solid(doc, man, p))


@op("add_sphere",
    doc="Add a sphere.",
    params={
        "center": P.point3(req=True),
        "radius": P.number(req=True, doc="radius (> 0)"),
        "segments": P.integer(default=0, doc="0 = automatic"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_sphere", "center": [0, 0, 500], "radius": 300},
    returns="{created: [id], volume, bbox}")
def add_sphere(doc, p):
    _check_segments(p)
    if p["radius"] <= 0:
        raise CadError("degenerate", "sphere needs a positive radius")
    man = Manifold.sphere(p["radius"], p["segments"]).translate(tuple(p["center"]))
    return _solid_result(doc, _add_solid(doc, man, p))


@op("add_torus",
    doc="Add a torus lying in the XY plane (donut axis = +Z through `at`).",
    params={
        "at": P.point3(default=[0.0, 0.0, 0.0], doc="center of the torus"),
        "radius": P.number(req=True, doc="ring radius: center to tube center"),
        "tube_radius": P.number(req=True, doc="tube radius (> 0, < radius)"),
        "segments": P.integer(default=0, doc="0 = automatic"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_torus", "at": [0, 0, 500], "radius": 400,
             "tube_radius": 80},
    returns="{created: [id], volume, bbox}")
def add_torus(doc, p):
    _check_segments(p)
    R, r = p["radius"], p["tube_radius"]
    if r <= 0:
        raise CadError("degenerate", "torus needs a positive tube_radius")
    if R <= r:
        raise CadError("degenerate",
                       f"ring radius {R} must exceed tube_radius {r}",
                       hint="a self-intersecting torus is not a manifold")
    # revolve the tube circle (profile x = distance from the +Z axis)
    circle = g.circle_points([R, 0.0], r,
                             p["segments"] or g.default_circle_segments(r))
    cs = CrossSection([circle], FillRule.Positive)
    man = cs.revolve(p["segments"] or g.default_circle_segments(R), 360.0)
    man = man.translate(tuple(p["at"]))
    return _solid_result(doc, _add_solid(doc, man, p))


@op("extrude",
    doc="Extrude closed 2D shapes vertically into solids (one solid per "
        "selected entity). The profile entities are kept unless keep=false.",
    params={
        "select": P.select(req=True, doc="closed shapes: circle / closed "
                                         "polyline / region / wall footprint"),
        "height": P.number(req=True, doc="extrusion height (+Z)"),
        "z": P.number(default=0.0, doc="base elevation"),
        "twist": P.number(default=0.0, doc="degrees of twist over the height"),
        "scale_top": P.number(default=1.0, doc="scale of the top vs the bottom"),
        "divisions": P.integer(default=0, doc="vertical subdivisions for twist"),
        "keep": P.boolean(default=True, doc="keep the profile entities"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "extrude", "select": "e2", "height": 3000},
    returns="{created: [ids], volume}")
def extrude(doc, p):
    ids = doc.select(p["select"])
    if not ids:
        raise CadError("empty_selection", "selector matched nothing")
    if p["height"] <= 0:
        raise CadError("degenerate", "extrusion height must be positive")
    created = []
    total_volume = 0.0
    for eid in ids:
        ent = doc.entities[eid]
        cs = shapes.to_cross_section(doc, ent)
        man = Manifold.extrude(cs, p["height"], p["divisions"], p["twist"],
                               (p["scale_top"], p["scale_top"]))
        if p["z"]:
            man = man.translate((0, 0, p["z"]))
        sid = _add_solid(doc, man, p)
        total_volume += shapes.solid_to_manifold(doc.entities[sid]).volume()
        created.append(sid)
    if not p["keep"]:
        doc.delete_entities(ids)
    return {"created": created, "volume": round(total_volume, 6)}


@op("revolve",
    doc="Revolve closed 2D profiles around the vertical axis through `axis_point` "
        "to make solids of revolution. In the profile, x = distance from the "
        "axis (must be >= 0 after shifting), y = height (becomes z).",
    params={
        "select": P.select(req=True, doc="closed profile(s)"),
        "angle": P.number(default=360.0, doc="sweep angle, degrees"),
        "axis_point": P.point2(default=[0.0, 0.0],
                               doc="2D point the vertical axis passes through "
                                   "(profile is measured from its x)"),
        "segments": P.integer(default=0, doc="0 = automatic"),
        "keep": P.boolean(default=True, doc="keep the profile entities"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "revolve", "select": "e3", "angle": 360},
    returns="{created: [ids]}")
def revolve(doc, p):
    _check_segments(p)
    ids = doc.select(p["select"])
    if not ids:
        raise CadError("empty_selection", "selector matched nothing")
    created = []
    ax, ay = p["axis_point"]
    for eid in ids:
        ent = doc.entities[eid]
        contours = shapes.entity_contours(doc, ent)
        # shift so the revolve axis is x=0; manifold revolves about the Y axis
        shifted = [[[x - ax, y - ay] for x, y in c] for c in contours]
        if min(x for c in shifted for x, _ in c) < -1e-9:
            raise CadError("degenerate",
                           f"profile {eid} crosses the revolve axis (x < {ax})",
                           hint="profiles must lie entirely on one side of the axis")
        cs = CrossSection(shifted, FillRule.Positive)
        man = cs.revolve(p["segments"], p["angle"]).translate((ax, ay, 0))
        sid = _add_solid(doc, man, p)
        created.append(sid)
    if not p["keep"]:
        doc.delete_entities(ids)
    return {"created": created}


@op("boolean_3d",
    doc="3D boolean between solids (walls are converted automatically). "
        "Inputs are consumed unless keep=true; result is one solid.",
    params={
        "kind": P.enum(["union", "difference", "intersect"], req=True,
               doc="boolean operation"),
        "a": P.select(req=True, doc="first operand(s), unioned together"),
        "b": P.select(doc="second operand(s); not needed for plain union"),
        "keep": P.boolean(default=False, doc="keep input entities"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "boolean_3d", "kind": "difference", "a": "e10", "b": "e11"},
    returns="{created: [id], volume, bbox}")
def boolean_3d(doc, p):
    a_ids = doc.select(p["a"])
    if not a_ids:
        raise CadError("empty_selection", "selector 'a' matched nothing")
    b_ids = doc.select(p["b"]) if p["b"] is not None else []
    overlap = set(a_ids) & set(b_ids)
    if overlap:
        raise CadError("bad_target",
                       f"entities {sorted(overlap)} are in both 'a' and 'b'")
    man_a = _union_manifold(doc, a_ids)
    if b_ids:
        man_b = _union_manifold(doc, b_ids)
        if p["kind"] == "union":
            result = man_a + man_b
        elif p["kind"] == "difference":
            result = man_a - man_b
        else:
            result = man_a ^ man_b
    else:
        if p["kind"] != "union":
            raise CadError("missing_param", f"{p['kind']} needs operand 'b'")
        result = man_a
    if result.is_empty():
        raise CadError("empty_result", "boolean produced an empty solid",
                       hint="check that the solids actually overlap")
    layer = p["layer"] or doc.entities[a_ids[0]]["layer"]
    material = p["material"] or doc.entities[a_ids[0]].get("material")
    if not p["keep"]:
        doc.delete_entities(a_ids + b_ids)
    p2 = dict(p)
    p2["layer"], p2["material"] = layer, material
    return _solid_result(doc, _add_solid(doc, result, p2))


def _union_manifold(doc, ids) -> Manifold:
    mans = [shapes.entity_to_manifold(doc, doc.entities[eid]) for eid in ids]
    return Manifold.batch_boolean(mans, OpType.Add) if len(mans) > 1 else mans[0]


# ------------------------------------------------------------- freeform

def _section_ring(doc, sel, samples: int) -> np.ndarray:
    ids = doc.select(sel)
    if len(ids) != 1:
        raise CadError("bad_target",
                       f"each section must match exactly 1 entity, got {len(ids)}")
    contours = shapes.entity_contours(doc, doc.entities[ids[0]])
    if len(contours) != 1:
        raise CadError("bad_target",
                       f"section {ids[0]} has {len(contours)} contours; "
                       "lofting needs single-contour profiles (no holes)")
    return g.resample_closed(g.ensure_ccw(contours[0]), samples), ids[0]


def _align_ring(prev: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Roll the ring's start index to minimize twist against the previous ring."""
    n = len(ring)
    best, best_d = 0, float("inf")
    for off in range(n):
        d = float(np.linalg.norm(np.roll(ring, -off, axis=0)[:, :2]
                                 - prev[:, :2], axis=1).sum())
        if d < best_d:
            best, best_d = off, d
    return np.roll(ring, -best, axis=0)


@op("loft",
    doc="Skin a solid through a stack of closed profiles at increasing "
        "heights (straight/ruled between sections — add more sections for "
        "curvature, or run 'smooth' after). Profiles may differ in shape: "
        "each is resampled to the same point count.",
    params={
        "sections": P.array(req=True,
                            doc='[{"select": <selector>, "z": height}, ...] '
                                "bottom to top, single-contour closed shapes"),
        "samples": P.integer(default=64, doc="points per section ring"),
        "divisions": P.integer(default=0,
                               doc="smooth interpolation: extra rings between "
                                   "sections, traced with a vertical spline "
                                   "(8-16 makes flowing surfaces; 0 = ruled)"),
        "keep": P.boolean(default=True, doc="keep the section entities"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "loft", "sections": [{"select": "e1", "z": 0},
                                        {"select": "e2", "z": 15000},
                                        {"select": "e3", "z": 30000}]},
    returns="{created: [id], volume, bbox}")
def loft(doc, p):
    secs = p["sections"]
    if not isinstance(secs, list) or len(secs) < 2:
        raise CadError("bad_param", "loft needs at least 2 sections")
    if p["samples"] < 8 or p["samples"] > 512:
        raise CadError("bad_param", "samples should be between 8 and 512")
    rings, used = [], []
    last_z = None
    for i, sec in enumerate(secs):
        if not isinstance(sec, dict) or "select" not in sec or "z" not in sec:
            raise CadError("bad_param",
                           f'section {i} should be {{"select": ..., "z": ...}}')
        try:
            z = float(doc.resolve(sec["z"]))
        except (TypeError, ValueError):
            raise CadError("bad_param", f"section {i}: z must be a number "
                                        "or expression")
        if not math.isfinite(z):
            raise CadError("bad_param", f"section {i}: z is not finite")
        if last_z is not None and z <= last_z:
            raise CadError("bad_param",
                           f"section {i}: z={z} must be above the previous "
                           f"section (z={last_z})")
        last_z = z
        ring2d, eid = _section_ring(doc, sec["select"], p["samples"])
        used.append(eid)
        ring = np.column_stack([ring2d, np.full(len(ring2d), z)])
        if rings:
            ring = _align_ring(rings[-1], ring)
        rings.append(ring)
    div = p["divisions"]
    if div:
        if not 1 <= div <= 64:
            raise CadError("bad_param", "divisions should be between 1 and 64")
        # trace each ring point vertically through all sections with a spline
        n = p["samples"]
        columns = []
        for j in range(n):
            col = [rings[i][j] for i in range(len(rings))]
            columns.append(np.asarray(g.catmull_rom(col, closed=False,
                                                    samples_per_seg=div + 1)))
        m = len(columns[0])
        rings = [np.stack([columns[j][i] for j in range(n)]) for i in range(m)]
    bottom = triangulate([rings[0][:, :2]])
    top = triangulate([rings[-1][:, :2]])
    man = shapes.solid_from_rings(rings, bottom, top)
    sid = _add_solid(doc, man, p)
    if not p["keep"]:
        doc.delete_entities(used)
    return _solid_result(doc, sid)


@op("sweep",
    doc="Sweep a closed profile along a 3D path to make a solid (tubes, "
        "ribbons, curved beams). The profile is centered on its own centroid "
        "and carried along the path with minimal twisting (parallel "
        "transport); profile x/y map to the path's normal/binormal.",
    params={
        "profile": P.select(req=True, doc="one closed single-contour shape"),
        "path": P.array(req=True, doc="[[x,y,z], ...] (open; >= 2 points)"),
        "smooth": P.boolean(default=True,
                            doc="spline the path through its points"),
        "twist": P.number(default=0.0, doc="degrees of twist over the path"),
        "scale_end": P.number(default=1.0, doc="profile scale at the far end"),
        "samples": P.integer(default=48, doc="points around the profile"),
        "keep": P.boolean(default=True, doc="keep the profile entity"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "sweep", "profile": "e1", "twist": 90,
             "path": [[0, 0, 0], [0, 2000, 6000], [0, 8000, 9000]]},
    returns="{created: [id], volume, bbox}")
def sweep(doc, p):
    raw = p["path"]
    if not isinstance(raw, list) or len(raw) < 2:
        raise CadError("bad_param", "path needs at least 2 points")
    if len(raw) > 10_000:
        raise CadError("over_budget", "path has more than 10k points")
    pts = []
    for q in raw:
        if not (isinstance(q, (list, tuple)) and len(q) in (2, 3) and
                all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in q)):
            raise CadError("bad_param",
                           f"path points must be finite [x, y, z], got {q!r}")
        pts.append(g.v3(q))
    if g.norm(pts[0] - pts[-1]) < 1e-9:
        raise CadError("bad_param", "closed sweep paths are not supported",
                       hint="leave the loop slightly open, or use revolve")
    if p["smooth"] and len(pts) >= 3:
        pts = [np.asarray(q) for q in g.catmull_rom(pts, samples_per_seg=8)]
    ring2d, eid = _section_ring(doc, p["profile"], p["samples"])
    centroid = ring2d.mean(axis=0)
    prof = ring2d - centroid

    m = len(pts)
    tangents = []
    for i in range(m):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, m - 1)]
        tangents.append(g.unit(b - a))
    # parallel-transport frames
    t0 = tangents[0]
    ref = np.array([0.0, 0.0, 1.0])
    if abs(float(t0 @ ref)) > 0.95:
        ref = np.array([1.0, 0.0, 0.0])
    normal = g.unit(ref - t0 * float(ref @ t0))
    frames = []
    arc = [0.0]
    for i in range(m):
        if i > 0:
            arc.append(arc[-1] + g.norm(pts[i] - pts[i - 1]))
            axis = np.cross(tangents[i - 1], tangents[i])
            s = g.norm(axis)
            c = float(tangents[i - 1] @ tangents[i])
            if s > 1e-9:
                rot = g.mat3_rotate_axis(axis, math.degrees(math.atan2(s, c)))
                normal = rot[:3, :3] @ normal
            normal = g.unit(normal - tangents[i] * float(normal @ tangents[i]))
        frames.append((normal.copy(), np.cross(tangents[i], normal)))
    total = arc[-1] or 1.0

    rings = []
    for i in range(m):
        s = arc[i] / total
        ang = math.radians(p["twist"]) * s
        sc = 1.0 + (p["scale_end"] - 1.0) * s
        ca, sa = math.cos(ang), math.sin(ang)
        n, b = frames[i]
        px = (prof[:, 0] * ca - prof[:, 1] * sa) * sc
        py = (prof[:, 0] * sa + prof[:, 1] * ca) * sc
        rings.append(pts[i] + px[:, None] * n + py[:, None] * b)
    caps = triangulate([prof])
    man = shapes.solid_from_rings(rings, caps, caps)
    sid = _add_solid(doc, man, p)
    if not p["keep"]:
        doc.delete_entities([eid])
    return _solid_result(doc, sid)


@op("deform",
    doc="Non-rigid deformation of solids (in place): twist about the "
        "vertical axis, taper along the height, or bend along x into an "
        "arc. Use refine to subdivide first so curved results look smooth.",
    params={
        "select": P.select(req=True, doc="solid entities"),
        "kind": P.enum(["twist", "taper", "bend"], req=True,
               doc="deformation type"),
        "amount": P.number(req=True,
                           doc="twist/bend: total degrees; taper: scale "
                               "factor at the top (e.g. 0.4)"),
        "plane": P.enum(["xz", "xy"], default="xz",
                        doc="bend only: bend vertically (xz) or in plan (xy)"),
        "refine": P.integer(default=3, doc="mesh subdivision before warping "
                                           "(0 = none)"),
    },
    example={"op": "deform", "select": {"tags": ["tower"]}, "kind": "twist",
             "amount": 120},
    returns="{modified: [ids]}")
def deform(doc, p):
    ids = [eid for eid in doc.select(p["select"])
           if doc.entities[eid]["type"] == "solid"]
    if not ids:
        raise CadError("empty_selection", "no solids in selection",
                       hint="walls: run solidify first")
    if not 0 <= p["refine"] <= 8:
        raise CadError("bad_param", "refine should be between 0 and 8")
    kind, amount = p["kind"], p["amount"]
    if kind in ("twist", "bend") and abs(amount) < 1e-9:
        raise CadError("bad_param", f"{kind} needs a non-zero amount")
    if kind == "taper" and amount < 0:
        raise CadError("bad_param", "taper amount must be >= 0")
    for eid in ids:
        ent = doc.entities[eid]
        man = shapes.solid_to_manifold(ent)
        if p["refine"]:
            man = man.refine(p["refine"] + 1)
        bb = man.bounding_box()
        lo, hi = np.array(bb[:3]), np.array(bb[3:])
        c = (lo + hi) / 2
        man = man.warp_batch(_warper(kind, amount, p["plane"], lo, hi, c))
        if man.is_empty():
            raise CadError("degenerate", f"deform collapsed solid {eid}",
                           hint="try a smaller amount")
        ent["mesh"] = shapes.mesh_to_dict(man)
    return {"modified": ids}


def _warper(kind, amount, plane, lo, hi, c):
    if kind == "twist":
        dz = max(hi[2] - lo[2], 1e-9)

        def f(pts):
            a = math.radians(amount) * (pts[:, 2] - lo[2]) / dz
            ca, sa = np.cos(a), np.sin(a)
            x = pts[:, 0] - c[0]
            y = pts[:, 1] - c[1]
            out = pts.copy()
            out[:, 0] = c[0] + x * ca - y * sa
            out[:, 1] = c[1] + x * sa + y * ca
            return out
        return f
    if kind == "taper":
        dz = max(hi[2] - lo[2], 1e-9)

        def f(pts):
            s = 1.0 + (amount - 1.0) * (pts[:, 2] - lo[2]) / dz
            out = pts.copy()
            out[:, 0] = c[0] + (pts[:, 0] - c[0]) * s
            out[:, 1] = c[1] + (pts[:, 1] - c[1]) * s
            return out
        return f
    # bend: along x, into an arc in the chosen plane
    k = 1 if plane == "xy" else 2  # the axis displaced by the bend
    span = max(hi[0] - lo[0], 1e-9)
    radius = span / math.radians(abs(amount))
    sign = 1.0 if amount > 0 else -1.0

    def f(pts):
        theta = (pts[:, 0] - c[0]) / radius
        r = radius - sign * (pts[:, k] - c[k])
        out = pts.copy()
        out[:, 0] = c[0] + r * np.sin(theta)
        out[:, k] = c[k] + sign * (radius - r * np.cos(theta))
        return out
    return f


@op("add_implicit",
    doc="Sculpt a solid from a math expression over x, y, z: the solid is "
        "where the expression is POSITIVE. The native way to make organic "
        "and freeform geometry. Helpers: length(...), smin/smax(a,b,k) for "
        "smooth blends, clamp, mix, abs, min, max, trig. Example sphere: "
        "'500 - length(x, y, z)'.",
    params={
        "expr": P.string(req=True, doc="scalar field; > 0 is solid"),
        "bounds": P.obj(req=True, doc='{"min": [x,y,z], "max": [x,y,z]} '
                                      "region to evaluate"),
        "edge_length": P.number(doc="mesh resolution (default: max extent/64; "
                                    "smaller = finer = slower)"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "add_implicit",
             "expr": "smax(400 - length(x, y, z), 300 - length(x - 350, y, z), 150)",
             "bounds": {"min": [-800, -800, -800], "max": [800, 800, 800]}},
    returns="{created: [id], volume, bbox}")
def add_implicit(doc, p):
    from ..expr import compile_field
    try:
        lo = [float(v) for v in p["bounds"]["min"]]
        hi = [float(v) for v in p["bounds"]["max"]]
        if len(lo) != 3 or len(hi) != 3:
            raise ValueError("bounds need 3 components")
        if not all(math.isfinite(v) for v in lo + hi):
            raise ValueError("non-finite bounds")
    except (KeyError, TypeError, ValueError):
        raise CadError("bad_param",
                       'bounds should be {"min": [x,y,z], "max": [x,y,z]} '
                       "with finite numbers")
    size = [hi[i] - lo[i] for i in range(3)]
    if min(size) <= 0:
        raise CadError("bad_param", "bounds max must exceed min on every axis")
    el = p["edge_length"] or max(size) / 64.0
    cells = (size[0] / el) * (size[1] / el) * (size[2] / el)
    if cells > 4e6:
        raise CadError("over_budget",
                       f"~{cells:.0f} cells exceeds the 4M budget",
                       hint="raise edge_length or shrink bounds")
    f = compile_field(p["expr"])
    try:
        f(lo[0], lo[1], lo[2])  # surface evaluation errors early
    except (ValueError, ZeroDivisionError, OverflowError) as e:
        raise CadError("bad_expr", f"expression failed to evaluate: {e}")
    man = Manifold.level_set(f, [*lo, *hi], el)
    if man.is_empty():
        raise CadError("empty_result",
                       "the field is never positive inside the bounds",
                       hint="check the sign convention: solid where expr > 0")
    return _solid_result(doc, _add_solid(doc, man, p))


@op("smooth",
    doc="Smooth solids in place: facet edges flatter than `angle` degrees "
        "are rounded into curvature-continuous patches (sharper edges are "
        "kept crisp), then the mesh is refined. Great after loft/deform.",
    params={
        "select": P.select(req=True, doc="solid entities"),
        "angle": P.number(default=52.5,
                          doc="edges with a dihedral angle below this get "
                              "smoothed; above it they stay sharp"),
        "refine": P.integer(default=3, doc="subdivision level (2-6 typical)"),
    },
    example={"op": "smooth", "select": {"tags": ["shell"]}, "angle": 60},
    returns="{modified: [ids], triangles}")
def smooth(doc, p):
    ids = [eid for eid in doc.select(p["select"])
           if doc.entities[eid]["type"] == "solid"]
    if not ids:
        raise CadError("empty_selection", "no solids in selection")
    if not 1 <= p["refine"] <= 8:
        raise CadError("bad_param", "refine should be between 1 and 8")
    total = 0
    for eid in ids:
        ent = doc.entities[eid]
        man = shapes.solid_to_manifold(ent)
        if man.num_tri() * (p["refine"] + 1) ** 2 > 800_000:
            raise CadError("over_budget",
                           f"smoothing {eid} would exceed the 800k-triangle "
                           "budget", hint="lower refine or simplify first")
        man = man.smooth_out(p["angle"]).refine(p["refine"] + 1)
        ent["mesh"] = shapes.mesh_to_dict(man)
        total += man.num_tri()
    return {"modified": ids, "triangles": total}


@op("solidify",
    doc="Convert walls into plain solid entities (so you can boolean them "
        "with other solids). The wall entity is replaced.",
    params={
        "select": P.select(req=True, doc="wall entities"),
        "material": P.material(),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "solidify", "select": {"types": ["wall"]}},
    returns="{created: [ids]}")
def solidify(doc, p):
    ids = doc.select(p["select"])
    walls = [eid for eid in ids if doc.entities[eid]["type"] == "wall"]
    if not walls:
        raise CadError("empty_selection", "no walls in selection")
    created = []
    for eid in walls:
        ent = doc.entities[eid]
        man = shapes.wall_to_manifold(doc, ent)
        p2 = dict(p)
        p2["layer"] = p["layer"] or ent["layer"]
        p2["material"] = p["material"] or ent.get("material")
        p2["tag"] = p["tag"] or ent.get("tag")
        sid = _add_solid(doc, man, p2)
        created.append(sid)
    doc.delete_entities(walls)
    return {"created": created}


@op("slice",
    doc="Horizontal section: cut solids/walls at height z and produce 2D "
        "region(s) of the cut. Sources are kept.",
    params={
        "select": P.select(default={"types": ["solid", "wall"]}),
        "z": P.number(req=True, doc="section height"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "slice", "select": "all", "z": 1200, "layer": "section"},
    returns="{created: [ids]}")
def slice_op(doc, p):
    ids = [eid for eid in doc.select(p["select"])
           if doc.entities[eid]["type"] in ("solid", "wall")]
    if not ids:
        raise CadError("empty_selection", "no solids or walls in selection")
    created = []
    for eid in ids:
        man = shapes.entity_to_manifold(doc, doc.entities[eid])
        cs = man.slice(p["z"])
        if cs.is_empty():
            continue
        data = shapes.cross_section_to_region(cs)
        created.append(doc.add_entity("region", data,
                                      layer=p["layer"] or "section",
                                      tag=p["tag"]))
    if not created:
        raise CadError("empty_result", f"nothing intersects z={p['z']}",
                       hint="check the solids' bounding boxes with list bbox=true")
    return {"created": created}


# view-axis remaps (right-handed): looking along z -> plan (x,y);
# along x -> elevation (y,z); along y -> elevation (x,z)
_PROJ_AXES = {
    "z": None,
    "x": np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0]], dtype=float),
    "y": np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0]], dtype=float),
}


@op("project",
    doc="Project solids/walls to a 2D outline region. axis 'z' gives the "
        "plan footprint (x,y); 'x' the side elevation outline (y,z); 'y' "
        "the front elevation outline (x,z). Sources are kept.",
    params={
        "select": P.select(default={"types": ["solid", "wall"]}),
        "axis": P.enum(["z", "x", "y"], default="z",
                       doc="viewing direction"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "project", "select": "e12", "axis": "y", "layer": "elevation"},
    returns="{created: [ids]}")
def project(doc, p):
    ids = [eid for eid in doc.select(p["select"])
           if doc.entities[eid]["type"] in ("solid", "wall")]
    if not ids:
        raise CadError("empty_selection", "no solids or walls in selection")
    remap = _PROJ_AXES[p["axis"]]
    created = []
    for eid in ids:
        man = shapes.entity_to_manifold(doc, doc.entities[eid])
        if remap is not None:
            man = man.transform(remap)
        cs = man.project()
        if cs.is_empty():
            continue
        data = shapes.cross_section_to_region(cs)
        created.append(doc.add_entity("region", data,
                                      layer=p["layer"] or
                                      ("footprint" if p["axis"] == "z"
                                       else "elevation"),
                                      tag=p["tag"]))
    return {"created": created}


@op("shell",
    doc="Hollow solids into shells of the given wall thickness (in place), "
        "by eroding a copy and subtracting it. Closed shells — combine with "
        "boolean_3d or slice to open them.",
    params={
        "select": P.select(req=True, doc="solid entities"),
        "thickness": P.number(req=True, doc="wall thickness (> 0)"),
        "segments": P.integer(default=12, doc="erosion sphere quality"),
    },
    example={"op": "shell", "select": {"tags": ["body"]}, "thickness": 2},
    returns="{modified: [ids]}")
def shell(doc, p):
    if p["thickness"] <= 0:
        raise CadError("bad_param", "thickness must be positive")
    ids = [eid for eid in doc.select(p["select"])
           if doc.entities[eid]["type"] == "solid"]
    if not ids:
        raise CadError("empty_selection", "no solids in selection",
                       hint="walls: run solidify first")
    ball = Manifold.sphere(p["thickness"], p["segments"])
    for eid in ids:
        ent = doc.entities[eid]
        man = shapes.solid_to_manifold(ent)
        core = man.minkowski_difference(ball)
        if core.is_empty():
            raise CadError("degenerate",
                           f"{eid} is thinner than 2x the shell thickness",
                           hint="reduce thickness")
        result = man - core
        if result.is_empty():
            raise CadError("empty_result", f"shelling {eid} produced nothing")
        ent["mesh"] = shapes.mesh_to_dict(result)
    return {"modified": ids}
