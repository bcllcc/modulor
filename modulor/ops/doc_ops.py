"""Document, layer, material and entity-management ops."""
from __future__ import annotations

from .. import shapes
from ..document import DEFAULT_LAYER, UNITS
from ..errors import CadError
from . import P, describe_op, list_ops, op


@op("doc_new",
    doc="Reset the document to an empty state.",
    params={
        "units": P.enum(UNITS, default="mm", doc="document units"),
        "name": P.string(default="untitled", doc="document name"),
    },
    example={"op": "doc_new", "units": "mm", "name": "bracket"},
    returns="{units, name}")
def doc_new(doc, p):
    path = doc.path  # keep the on-disk location across the reset
    doc.__init__(units=p["units"], name=p["name"])
    doc.path = path
    return {"units": doc.units, "name": doc.meta["name"]}


@op("doc_info",
    doc="Summary of the document: units, layers, entity counts, bounding box.",
    params={},
    example={"op": "doc_info"},
    returns="{units, name, layers, counts, bbox}", effects="none")
def doc_info(doc, p):
    counts: dict[str, int] = {}
    for ent in doc.entities.values():
        counts[ent["type"]] = counts.get(ent["type"], 0) + 1
    return {
        "units": doc.units,
        "name": doc.meta.get("name"),
        "layers": list(doc.layers.keys()),
        "materials": list(doc.materials.keys()),
        "entities": len(doc.entities),
        "counts": counts,
        "bbox": shapes.doc_bbox(doc).as_dict(),
    }


@op("set_units",
    doc="Change document units (does NOT rescale existing geometry).",
    params={"units": P.enum(UNITS, req=True, doc="new document units")},
    example={"op": "set_units", "units": "m"},
    returns="{units}")
def set_units(doc, p):
    doc.units = p["units"]
    return {"units": doc.units}


@op("add_layer",
    doc="Create or update a layer. Layers are also auto-created when first "
        "referenced by a drawing op.",
    params={
        "name": P.string(req=True, doc="layer name"),
        "color": P.string(default=None, doc="'#rrggbb'"),
        "line_width": P.number(doc="display/print line width"),
        "visible": P.boolean(doc="hidden layers are skipped by render/export"),
    },
    example={"op": "add_layer", "name": "walls", "color": "#333333"},
    returns="{layer, color, visible, line_width}")
def add_layer(doc, p):
    layer = doc.layers.setdefault(p["name"], dict(DEFAULT_LAYER))
    if p["color"] is not None:
        shapes.parse_color(p["color"])  # validate
        layer["color"] = p["color"]
    if p["line_width"] is not None:
        layer["line_width"] = p["line_width"]
    if p["visible"] is not None:
        layer["visible"] = p["visible"]
    return {"layer": p["name"], **layer}


@op("list_layers",
    doc="List layers and their properties.",
    params={},
    example={"op": "list_layers"},
    returns="{layers: {name: {color, visible, line_width}}}",
    effects="none")
def list_layers(doc, p):
    return {"layers": {k: dict(v) for k, v in doc.layers.items()}}


@op("add_material",
    doc="Create or update a material (used by 3D solids; exported to glTF/OBJ).",
    params={
        "name": P.string(req=True, doc="material name"),
        "color": P.string(req=True, doc="'#rrggbb'"),
        "metallic": P.number(default=0.0, doc="PBR metallic, 0-1"),
        "roughness": P.number(default=0.8, doc="PBR roughness, 0-1"),
    },
    example={"op": "add_material", "name": "concrete", "color": "#b8b4ab"},
    returns="{material, color, metallic, roughness}")
def add_material(doc, p):
    shapes.parse_color(p["color"])  # validate
    doc.materials[p["name"]] = {"color": p["color"],
                                "metallic": p["metallic"],
                                "roughness": p["roughness"]}
    return {"material": p["name"], **doc.materials[p["name"]]}


@op("list",
    doc="List entities (id, type, layer, tag and a one-line geometric summary).",
    params={
        "select": P.select(default="all"),
        "bbox": P.boolean(default=False, doc="include per-entity bounding boxes"),
    },
    example={"op": "list", "select": {"layers": ["walls"]}},
    returns="{entities: [{id, type, layer, tag?, brief, bbox?}]}",
    effects="none")
def list_entities(doc, p):
    ids = doc.select(p["select"])
    out = []
    for eid in ids:
        ent = doc.entities[eid]
        row = {"id": eid, "type": ent["type"], "layer": ent["layer"],
               "brief": _brief(ent)}
        if ent.get("tag"):
            row["tag"] = ent["tag"]
        if p["bbox"]:
            row["bbox"] = shapes.entity_bbox(doc, eid).as_dict()
        out.append(row)
    return {"count": len(out), "entities": out}


def _brief(ent) -> str:
    t = ent["type"]
    r = lambda v: round(v, 3)  # noqa: E731
    if t == "line":
        return f"({r(ent['start'][0])},{r(ent['start'][1])}) -> " \
               f"({r(ent['end'][0])},{r(ent['end'][1])})"
    if t in ("polyline", "spline"):
        return f"{len(ent['points'])} pts" + (", closed" if ent.get("closed") else "")
    if t == "circle":
        return f"c=({r(ent['center'][0])},{r(ent['center'][1])}) r={r(ent['radius'])}"
    if t == "arc":
        return f"r={r(ent['radius'])} {r(ent['start_angle'])}deg->{r(ent['end_angle'])}deg"
    if t == "region":
        return f"{len(ent['contours'])} contour(s)"
    if t == "text":
        s = ent["text"]
        return repr(s if len(s) <= 24 else s[:21] + "...")
    if t == "dim":
        return f"({r(ent['p1'][0])},{r(ent['p1'][1])}) -> ({r(ent['p2'][0])},{r(ent['p2'][1])})"
    if t == "wall":
        n = len(ent.get("openings", []))
        return f"{len(ent['path'])} pts, t={r(ent['thickness'])}" + \
               (f", {n} opening(s)" if n else "")
    if t == "solid":
        return f"{len(ent['mesh']['triangles'])} tris, mat={ent.get('material', 'default')}"
    if t == "grid":
        return f"{len(ent['xs'])} x {len(ent['ys'])} axes"
    if t == "room":
        lvl = f" @{ent['level']}" if ent.get("level") else ""
        return f"{ent['name']}{lvl}, {round(abs(_area(ent['points'])), 1)}"
    return ""


def _area(pts):
    from .. import geometry as _g
    return _g.polygon_area(pts)


@op("get",
    doc="Full data of one entity, including geometry.",
    params={"id": P.string(req=True, doc="entity id, e.g. 'e3'")},
    example={"op": "get", "id": "e3"},
    returns="{id, entity, bbox}", effects="none")
def get_entity(doc, p):
    ids = doc.select(p["id"])
    if len(ids) != 1:
        raise CadError("bad_target",
                       f"'id' must name exactly one entity, matched {len(ids)}",
                       hint="use the 'list' op for bulk inspection")
    eid = ids[0]
    return {"id": eid, "entity": doc.entities[eid],
            "bbox": shapes.entity_bbox(doc, eid).as_dict()}


@op("update",
    doc="Change non-geometric properties of entities: layer, tag, material.",
    params={
        "select": P.select(req=True),
        "layer": P.layer(),
        "tag": P.tag(),
        "material": P.string(doc="material name (solids/walls)"),
    },
    example={"op": "update", "select": "e3", "layer": "furniture"},
    returns="{modified: [ids]}")
def update_entity(doc, p):
    ids = doc.select(p["select"])
    if not ids:
        raise CadError("empty_selection", "selector matched nothing",
                       hint="use the 'list' op to inspect the document")
    for eid in ids:
        ent = doc.entities[eid]
        if p["layer"] is not None:
            if p["layer"] not in doc.layers:
                doc.layers[p["layer"]] = dict(DEFAULT_LAYER)
            ent["layer"] = p["layer"]
        if p["tag"] is not None:
            ent["tag"] = p["tag"]
        if p["material"] is not None:
            if p["material"] not in doc.materials:
                raise CadError("not_found", f"material {p['material']!r} not defined",
                               hint="create it first with add_material")
            ent["material"] = p["material"]
    return {"modified": ids}


@op("delete",
    doc="Delete entities.",
    params={"select": P.select(req=True)},
    example={"op": "delete", "select": {"layers": ["draft"]}},
    returns="{deleted: n}")
def delete(doc, p):
    ids = doc.select(p["select"])
    if not ids:
        raise CadError("empty_selection", "selector matched nothing",
                       hint="use the 'list' op to inspect the document")
    n = doc.delete_entities(ids)
    return {"deleted": n}


def _snap_dir(doc) -> str:
    if not doc.path:
        raise CadError("no_path", "snapshots need a document file",
                       hint="save the document first (it has no path yet)")
    return doc.path + ".snapshots"


@op("snapshot",
    doc="Save a named snapshot of the whole document (cheap insurance "
        "before risky boolean/transform sequences).",
    params={"name": P.string(doc="snapshot name (default: timestamp)")},
    example={"op": "snapshot", "name": "before-booleans"},
    returns="{snapshot, entities}", effects="files")
def snapshot(doc, p):
    import json as _json
    import os
    import re
    import time
    name = p["name"] or time.strftime("%Y%m%d-%H%M%S")
    if not re.fullmatch(r"[\w.-]+", name):
        raise CadError("bad_param", f"snapshot name {name!r} should be "
                                    "letters/digits/dot/dash/underscore")
    d = _snap_dir(doc)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(doc.to_dict(), f, ensure_ascii=False, separators=(",", ":"))
    return {"snapshot": name, "entities": len(doc.entities)}


@op("restore",
    doc="Replace the document with a previously saved snapshot.",
    params={"name": P.string(req=True, doc="snapshot name")},
    example={"op": "restore", "name": "before-booleans"},
    returns="{restored, entities}")
def restore(doc, p):
    import json as _json
    import os
    path = os.path.join(_snap_dir(doc), p["name"] + ".json")
    if not os.path.exists(path):
        raise CadError("not_found", f"no snapshot named {p['name']!r}",
                       hint="list them with the 'snapshots' op")
    from ..document import Document
    with open(path, "r", encoding="utf-8") as f:
        loaded = Document.from_dict(_json.load(f))
    doc.units = loaded.units
    doc.meta = loaded.meta
    doc.layers = loaded.layers
    doc.materials = loaded.materials
    doc.entities = loaded.entities
    doc._counter = loaded._counter
    return {"restored": p["name"], "entities": len(doc.entities)}


@op("snapshots",
    doc="List saved snapshots of this document.",
    params={},
    example={"op": "snapshots"},
    returns="{snapshots: [{name, modified, size}]}", effects="none")
def snapshots(doc, p):
    import os
    import time
    d = _snap_dir(doc)
    out = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                st = os.stat(os.path.join(d, fn))
                out.append({"name": fn[:-5], "size": st.st_size,
                            "modified": time.strftime("%Y-%m-%dT%H:%M:%S",
                                                      time.localtime(st.st_mtime))})
    return {"snapshots": out}


@op("help",
    doc="Introspect the API: list all ops, or full parameter docs for one op.",
    params={"name": P.string(doc="op name; omit to list all ops")},
    example={"op": "help", "name": "add_wall"},
    returns="{ops: [{op, doc, effects}]} or one op's full description",
    effects="none")
def help_op(doc, p):
    if p["name"]:
        return describe_op(p["name"])
    return {"ops": list_ops(),
            "note": "call {\"op\": \"help\", \"name\": \"<op name>\"} for params"}
