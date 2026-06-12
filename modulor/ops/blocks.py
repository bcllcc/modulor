"""Block ops: reusable component definitions and instances.

A block is a named group of entity records stored once in the document;
an instance places it with a position, rotation and uniform scale. The
DXF exporter writes them as native BLOCKS/INSERT; everything else
(render, measure, booleans, transforms) sees instances through expansion.
"""
from __future__ import annotations

import copy as _copy

from .. import shapes
from ..errors import CadError
from . import P, op

MAX_BLOCK_ENTITIES = 10_000


@op("define_block",
    doc="Define a reusable block from existing entities. By default the "
        "source entities are replaced by one instance in place (geometry "
        "is unchanged); pass replace=false to keep them and only store "
        "the definition.",
    params={
        "select": P.select(req=True, doc="entities to capture (grids cannot "
                                         "be blocked)"),
        "name": P.string(req=True, doc="block name (must be new)"),
        "base": P.point2(default=[0.0, 0.0],
                         doc="local origin: insert_block 'at' lands here"),
        "replace": P.boolean(default=True,
                             doc="swap the source entities for an instance"),
    },
    example={"op": "define_block", "select": {"tags": ["window"]},
             "name": "win-900", "base": [0, 0]},
    returns="{created: [instance id] or [], block, count}")
def define_block(doc, p):
    name = p["name"]
    if not name or "/" in name:
        raise CadError("bad_param", "block names must be non-empty, no '/'")
    if name in doc.blocks:
        raise CadError("bad_param", f"block {name!r} already exists",
                       hint="block definitions are immutable; pick a new name")
    ids = doc.select(p["select"])
    if not ids:
        raise CadError("empty_selection", "selector matched nothing")
    if len(ids) > MAX_BLOCK_ENTITIES:
        raise CadError("over_budget",
                       f"{len(ids)} entities exceeds the block budget "
                       f"of {MAX_BLOCK_ENTITIES}")
    for eid in ids:
        if doc.entities[eid]["type"] == "grid":
            raise CadError("bad_type",
                           "grids define the document axis system and "
                           "cannot be part of a block")
    # definitions can only reference earlier blocks, so cycles cannot form
    entities = [_copy.deepcopy(doc.entities[eid]) for eid in ids]
    doc.blocks[name] = {"base": [float(p["base"][0]), float(p["base"][1])],
                        "entities": entities}
    created = []
    if p["replace"]:
        doc.delete_entities(ids)
        eid = doc.add_entity("instance",
                             {"block": name, "at": list(doc.blocks[name]["base"]),
                              "rotation": 0.0, "scale": 1.0},
                             layer=entities[0].get("layer", "0"))
        created.append(eid)
    return {"created": created, "block": name, "count": len(entities)}


@op("insert_block",
    doc="Place an instance of a block: the block's base point lands on "
        "`at`, rotated and uniformly scaled. Use array/copy for repetition.",
    params={
        "name": P.string(req=True, doc="a defined block (see define_block)"),
        "at": P.point2(req=True, doc="insertion point"),
        "rotation": P.number(default=0.0, doc="degrees CCW"),
        "scale": P.number(default=1.0, doc="uniform factor (> 0)"),
        "layer": P.layer(),
        "tag": P.tag(),
    },
    example={"op": "insert_block", "name": "win-900", "at": [3200, 0],
             "rotation": 90},
    returns="{created: [id]}")
def insert_block(doc, p):
    if p["scale"] <= 0:
        raise CadError("bad_param", "scale must be positive",
                       hint="mirroring is not supported on instances; "
                            "mirror the source entities instead")
    shapes.get_block(doc, p["name"])  # not_found with a hint if missing
    ent = {"block": p["name"], "at": p["at"],
           "rotation": p["rotation"], "scale": p["scale"]}
    eid = doc.add_entity("instance", ent, layer=p["layer"] or "0",
                         tag=p["tag"])
    # validate-before-mutate: the placement must expand cleanly
    try:
        shapes.expand_instance(doc, doc.entities[eid])
    except CadError:
        del doc.entities[eid]
        raise
    return {"created": [eid]}
