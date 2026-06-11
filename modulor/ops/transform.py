"""Transform ops: move / copy / rotate / scale / mirror / array.

One implementation handles both 2D entities (3x3 affine) and solids
(4x4 affine applied through the manifold kernel).
"""
from __future__ import annotations

import copy as _copy
import math

import numpy as np

from .. import geometry as g
from .. import shapes
from ..errors import CadError
from . import P, op


# ---------------------------------------------------------------- core

def _transform_entity(doc, eid: str, m2: np.ndarray, m3: np.ndarray | None = None):
    """Apply an affine transform to one entity in place."""
    ent = doc.entities[eid]
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
    elif t == "text":
        _need_uniform(t, uniform)
        ent["at"] = g.apply2(m2, ent["at"])
        ent["height"] = ent["height"] * factor
        if not flips:
            ent["rotation"] = ent.get("rotation", 0.0) + g.mat2_angle(m2)
        # mirrored text stays readable: position moves, glyphs don't flip
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
    elif t == "solid":
        man = shapes.solid_to_manifold(ent)
        m3 = m3 if m3 is not None else g.mat3_from_mat2(m2)
        man = man.transform(g.mat3_to_manifold(m3))
        if man.is_empty():
            raise CadError("degenerate", f"transform collapsed solid {eid}")
        ent["mesh"] = shapes.mesh_to_dict(man)
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


def _clone(doc, eid: str) -> str:
    ent = _copy.deepcopy(doc.entities[eid])
    new_id = doc.new_id()
    doc.entities[new_id] = ent
    return new_id


# ---------------------------------------------------------------- ops

@op("move",
    doc="Translate entities by a vector. 2D entities ignore dz.",
    params={
        "select": P.select(req=True),
        "by": P.point3(req=True, doc="[dx, dy] or [dx, dy, dz]"),
    },
    example={"op": "move", "select": ["e1", "e2"], "by": [0, 2500]},
    returns="{modified: [ids]}")
def move(doc, p):
    ids = _sel(doc, p["select"])
    dx, dy, dz = p["by"]
    m2 = g.mat2_translate(dx, dy)
    m3 = g.mat3_translate(dx, dy, dz)
    for eid in ids:
        _transform_entity(doc, eid, m2, m3)
    return {"modified": ids}


@op("copy",
    doc="Copy entities, translating each copy by `by` (repeated `count` times).",
    params={
        "select": P.select(req=True),
        "by": P.point3(req=True, doc="[dx, dy] or [dx, dy, dz] per copy"),
        "count": P.integer(default=1, doc="number of copies"),
    },
    example={"op": "copy", "select": "e5", "by": [3000, 0], "count": 3},
    returns="{created: [ids]}")
def copy_op(doc, p):
    ids = _sel(doc, p["select"])
    if p["count"] < 1:
        raise CadError("bad_param", "count must be >= 1")
    if p["count"] * len(ids) > 10_000:
        raise CadError("over_budget",
                       f"{p['count']} copies of {len(ids)} entities exceeds "
                       "the 10k budget")
    dx, dy, dz = p["by"]
    created = []
    for i in range(1, p["count"] + 1):
        m2 = g.mat2_translate(dx * i, dy * i)
        m3 = g.mat3_translate(dx * i, dy * i, dz * i)
        for eid in ids:
            nid = _clone(doc, eid)
            _transform_entity(doc, nid, m2, m3)
            created.append(nid)
    return {"created": created}


@op("rotate",
    doc="Rotate entities CCW (degrees). 2D rotation is about `center` in the "
        "plane; solids rotate about a vertical axis through `center` unless "
        "`axis` is given.",
    params={
        "select": P.select(req=True),
        "angle": P.number(req=True, doc="degrees CCW"),
        "center": P.point3(default=[0.0, 0.0, 0.0]),
        "axis": P.point3(doc="rotation axis for solids (default [0,0,1])"),
    },
    example={"op": "rotate", "select": "e7", "angle": 90, "center": [500, 500]},
    returns="{modified: [ids]}")
def rotate(doc, p):
    ids = _sel(doc, p["select"])
    c = p["center"]
    m2 = g.mat2_rotate(p["angle"], center=c[:2])
    axis = p["axis"] or [0.0, 0.0, 1.0]
    m3 = g.mat3_rotate_axis(axis, p["angle"], point=c)
    if p["axis"] is not None and any(abs(v) > 1e-12 for v in axis[:2]):
        # non-vertical axis only makes sense for solids
        for eid in ids:
            if doc.entities[eid]["type"] != "solid":
                raise CadError("bad_param",
                               "non-vertical axis rotation only applies to solids")
    for eid in ids:
        _transform_entity(doc, eid, m2, m3)
    return {"modified": ids}


@op("scale",
    doc="Scale entities about a center point. Pass one factor for uniform "
        "scaling or [fx, fy] / [fx, fy, fz].",
    params={
        "select": P.select(req=True),
        "factor": P.obj(req=True, doc="number or [fx, fy] or [fx, fy, fz]"),
        "center": P.point3(default=[0.0, 0.0, 0.0]),
    },
    example={"op": "scale", "select": "e2", "factor": 2.0, "center": [0, 0]},
    returns="{modified: [ids]}")
def scale(doc, p):
    ids = _sel(doc, p["select"])
    f = p["factor"]
    if isinstance(f, (int, float)) and not isinstance(f, bool):
        fx = fy = fz = float(f)
    elif (isinstance(f, (list, tuple)) and len(f) in (2, 3) and
          all(isinstance(v, (int, float)) and not isinstance(v, bool)
              for v in f)):
        fx, fy = float(f[0]), float(f[1])
        fz = float(f[2]) if len(f) == 3 else 1.0
    else:
        raise CadError("bad_param", f"factor should be a number or [fx, fy(, fz)], "
                                    f"got {f!r}")
    if not all(math.isfinite(v) and abs(v) < 1e9 for v in (fx, fy, fz)):
        raise CadError("bad_param", "scale factors must be finite")
    if min(abs(fx), abs(fy), abs(fz)) < 1e-12:
        raise CadError("degenerate", "zero scale factor")
    c = p["center"]
    m2 = g.mat2_scale(fx, fy, center=c[:2])
    m3 = g.mat3_scale(fx, fy, fz, center=c)
    for eid in ids:
        _transform_entity(doc, eid, m2, m3)
    return {"modified": ids}


@op("mirror",
    doc="Mirror entities across the line p1->p2 (solids: across the vertical "
        "plane through that line). Set copy=true to keep the original.",
    params={
        "select": P.select(req=True),
        "p1": P.point2(req=True),
        "p2": P.point2(req=True),
        "copy": P.boolean(default=False, doc="keep the original"),
    },
    example={"op": "mirror", "select": "e4", "p1": [0, 0], "p2": [0, 100],
             "copy": True},
    returns="{modified: [ids]} or {created: [ids]}")
def mirror(doc, p):
    ids = _sel(doc, p["select"])
    m2 = g.mat2_mirror(p["p1"], p["p2"])
    m3 = g.mat3_mirror_plane(p["p1"], p["p2"])
    if p["copy"]:
        created = []
        for eid in ids:
            nid = _clone(doc, eid)
            _transform_entity(doc, nid, m2, m3)
            created.append(nid)
        return {"created": created}
    for eid in ids:
        _transform_entity(doc, eid, m2, m3)
    return {"modified": ids}


@op("array",
    doc="Repeat entities in a grid or around a center (polar). The original "
        "counts as the first item.",
    params={
        "select": P.select(req=True),
        "kind": P.enum(["grid", "polar"], req=True,
                       doc="rectangular lattice or around a center"),
        "nx": P.integer(default=1, doc="grid: columns"),
        "ny": P.integer(default=1, doc="grid: rows"),
        "dx": P.number(default=0.0, doc="grid: column spacing"),
        "dy": P.number(default=0.0, doc="grid: row spacing"),
        "count": P.integer(doc="polar: total item count"),
        "center": P.point2(default=[0.0, 0.0], doc="polar: rotation center"),
        "angle": P.number(default=360.0, doc="polar: total angle (degrees)"),
    },
    example={"op": "array", "select": "e9", "kind": "grid",
             "nx": 4, "ny": 2, "dx": 3000, "dy": 4000},
    returns="{created: [ids]}")
def array(doc, p):
    ids = _sel(doc, p["select"])
    created = []
    if p["kind"] == "grid":
        if p["nx"] < 1 or p["ny"] < 1:
            raise CadError("bad_param", "nx and ny must be >= 1")
        if p["nx"] * p["ny"] * len(ids) > 10_000:
            raise CadError("over_budget",
                           f"{p['nx']}x{p['ny']} grid of {len(ids)} entities "
                           "exceeds the 10k budget")
        for iy in range(p["ny"]):
            for ix in range(p["nx"]):
                if ix == 0 and iy == 0:
                    continue
                m2 = g.mat2_translate(p["dx"] * ix, p["dy"] * iy)
                m3 = g.mat3_translate(p["dx"] * ix, p["dy"] * iy, 0)
                for eid in ids:
                    nid = _clone(doc, eid)
                    _transform_entity(doc, nid, m2, m3)
                    created.append(nid)
    else:  # polar
        n = p["count"]
        if not n or n < 2:
            raise CadError("bad_param", "polar array needs count >= 2")
        if n * len(ids) > 10_000:
            raise CadError("over_budget",
                           f"{n} polar items of {len(ids)} entities exceeds "
                           "the 10k budget")
        full = abs(p["angle"] - 360.0) < 1e-9 or abs(p["angle"]) < 1e-9
        steps = n if full else n - 1
        for i in range(1, n):
            ang = p["angle"] * i / steps
            m2 = g.mat2_rotate(ang, center=p["center"])
            m3 = g.mat3_rotate_axis([0, 0, 1], ang,
                                    point=[p["center"][0], p["center"][1], 0])
            for eid in ids:
                nid = _clone(doc, eid)
                _transform_entity(doc, nid, m2, m3)
                created.append(nid)
    return {"created": created}


def _sel(doc, sel) -> list[str]:
    ids = doc.select(sel)
    if not ids:
        raise CadError("empty_selection", "selector matched nothing",
                       hint="use the 'list' op to inspect the document")
    return ids
