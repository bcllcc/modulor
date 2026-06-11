"""Parametric design ops.

The agent-native answer to "change the column bay from 4m to 5m and keep
everything coordinated" is NOT a constraint solver — it is making the
generating program a first-class part of the document:

  - numeric fields in ANY op accept expressions: "bay*3", "level('L2')+900"
  - `recipe_set` stores the command list that builds the model
  - `set_param` + `regenerate` rebuild the whole model from the recipe

The recipe IS the design intent, and it survives in the document file.
"""
from __future__ import annotations

import json
import os
import re

from ..errors import CadError
from . import P, op

_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED = {"x", "y", "z", "pi", "e", "tau", "level", "level_top",
             "grid_x", "grid_y"}
_RECIPE_FORBIDDEN = {"doc_new", "regenerate", "recipe_set", "restore"}


def _check_name(name: str):
    if not _NAME_RE.match(name) or name in _RESERVED:
        raise CadError("bad_param",
                       f"{name!r} is not a usable parameter name",
                       hint="letters/digits/underscore, not starting with a "
                            f"digit, and not one of {sorted(_RESERVED)}")


@op("define_param",
    doc="Declare a design parameter with a default value — sets it only if "
        "it does not exist yet. Use this inside recipes so `regenerate` "
        "overrides are not clobbered.",
    params={
        "name": P.string(req=True, doc="parameter name (identifier)"),
        "value": P.number(req=True, doc="default value"),
    },
    example={"op": "define_param", "name": "bay", "value": 4000},
    returns="{name, value, defined}")
def define_param(doc, p):
    _check_name(p["name"])
    if p["name"] in doc.params:
        return {"name": p["name"], "value": doc.params[p["name"]],
                "defined": False}
    doc.params[p["name"]] = p["value"]
    return {"name": p["name"], "value": p["value"], "defined": True}


@op("set_param",
    doc="Set a design parameter. Any numeric field in any op can reference "
        "it by name in an expression: {\"width\": \"bay*2\"}. Combine with "
        "`regenerate` to rebuild the model with the new value.",
    params={
        "name": P.string(req=True, doc="parameter name (identifier)"),
        "value": P.number(req=True, doc="new value"),
    },
    example={"op": "set_param", "name": "bay", "value": 5000},
    returns="{name, value}")
def set_param(doc, p):
    _check_name(p["name"])
    doc.params[p["name"]] = p["value"]
    return {"name": p["name"], "value": p["value"]}


@op("params",
    doc="List design parameters, levels and the stored recipe size.",
    params={},
    example={"op": "params"},
    returns="{params, levels, recipe_commands}", effects="none")
def params_op(doc, p):
    return {"params": dict(doc.params),
            "levels": {k: dict(v) for k, v in doc.levels.items()},
            "recipe_commands": len(doc.recipe)}


@op("add_level",
    doc="Define a named building level (storey). Reference it anywhere a "
        "number is accepted: \"level('L2')\" is its elevation, "
        "\"level_top('L2')\" is elevation + height.",
    params={
        "name": P.string(req=True, doc="e.g. 'L1', 'roof'"),
        "elevation": P.number(req=True, doc="level elevation (z)"),
        "height": P.number(doc="storey height (enables level_top)"),
    },
    example={"op": "add_level", "name": "L2", "elevation": 3200, "height": 3200},
    returns="{levels}")
def add_level(doc, p):
    lv = {"elevation": p["elevation"]}
    if p["height"] is not None:
        lv["height"] = p["height"]
    doc.levels[p["name"]] = lv
    return {"levels": {k: dict(v) for k, v in doc.levels.items()}}


@op("recipe_set",
    doc="Store the command list that generates this model (the design "
        "intent). After this, `regenerate` rebuilds the whole model from "
        "the recipe — typically after `set_param`. Use `define_param` "
        "inside the recipe for defaults.",
    params={
        "commands": P.array(req=True, doc="ordered op commands; expressions "
                                          "in numeric fields are kept live"),
        "run": P.boolean(default=False,
                         doc="also regenerate from it immediately"),
    },
    example={"op": "recipe_set", "commands": [
        {"op": "define_param", "name": "bay", "value": 4000},
        {"op": "add_grid", "x": {"start": 0, "count": 5, "spacing": "bay"},
         "y": {"start": 0, "count": 3, "spacing": "bay*1.5"}}],
        "run": True},
    returns="{recipe_commands}")
def recipe_set(doc, p):
    cmds = p["commands"]
    if not isinstance(cmds, list) or not cmds:
        raise CadError("bad_param", "commands must be a non-empty list")
    for i, c in enumerate(cmds):
        if not isinstance(c, dict) or "op" not in c:
            raise CadError("bad_param", f"command {i} is not an op object")
        if c["op"] in _RECIPE_FORBIDDEN:
            raise CadError("bad_param",
                           f"command {i}: {c['op']!r} cannot be part of a "
                           "recipe")
    doc.recipe = [dict(c) for c in cmds]
    out = {"recipe_commands": len(doc.recipe)}
    if p["run"]:
        out.update(regenerate(doc, {"params": None}))
    return out


@op("regenerate",
    doc="Rebuild the model from the stored recipe: geometry is cleared, "
        "parameters survive (optionally overridden), every expression is "
        "re-evaluated. This is how a design stays coordinated when a "
        "parameter changes.",
    params={
        "params": P.obj(doc='{"name": value, ...} parameter overrides '
                            "applied before rebuilding"),
    },
    example={"op": "regenerate", "params": {"bay": 5000}},
    returns="{regenerated, entities, params}")
def regenerate(doc, p):
    if getattr(doc, "_regenerating", False):
        raise CadError("recipe_error", "regenerate cannot run inside a recipe")
    if not doc.recipe:
        raise CadError("recipe_error", "this document has no stored recipe",
                       hint="store one with recipe_set")
    overrides = p.get("params") or {}
    if not isinstance(overrides, dict):
        raise CadError("bad_param",
                       'params should be an object like {"bay": 5000}')
    for k, v in overrides.items():
        _check_name(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CadError("bad_param", f"override {k!r} must be a number")
        doc.params[k] = float(v)

    keep_path, keep_params = doc.path, dict(doc.params)
    keep_recipe, keep_units = list(doc.recipe), doc.units
    keep_name = doc.meta.get("name", "untitled")
    doc.__init__(units=keep_units, name=keep_name)
    doc.path = keep_path
    doc.params = keep_params
    doc.recipe = keep_recipe

    doc._regenerating = True
    try:
        from ..engine import BatchError, run_batch
        try:
            run_batch(doc, doc.recipe)
        except BatchError as e:
            raise CadError("recipe_error",
                           f"recipe command {e.index} ({e.opname}) failed: "
                           f"{e.message}", hint=e.hint)
    finally:
        doc._regenerating = False
    return {"regenerated": True, "entities": len(doc.entities),
            "params": dict(doc.params)}


@op("diff",
    doc="Compare the current model against a saved snapshot: parameter "
        "changes, entity additions/removals/modifications, and metric "
        "deltas. The review tool for design options.",
    params={
        "against": P.string(req=True, doc="snapshot name (see 'snapshots')"),
    },
    example={"op": "diff", "against": "option-a"},
    returns="{params_changed, added, removed, modified, metrics}",
    effects="none")
def diff(doc, p):
    from ..document import Document
    from .doc_ops import _snap_dir
    path = os.path.join(_snap_dir(doc), p["against"] + ".json")
    if not os.path.exists(path):
        raise CadError("not_found", f"no snapshot named {p['against']!r}",
                       hint="list them with the 'snapshots' op")
    with open(path, "r", encoding="utf-8") as f:
        other = Document.from_dict(json.load(f))

    params_changed = {}
    for k in sorted(set(doc.params) | set(other.params)):
        a, b = other.params.get(k), doc.params.get(k)
        if a != b:
            params_changed[k] = {"from": a, "to": b}

    cur, old = doc.entities, other.entities
    added = [e for e in cur if e not in old]
    removed = [e for e in old if e not in cur]
    modified = [e for e in cur if e in old and cur[e] != old[e]]

    return {
        "against": p["against"],
        "params_changed": params_changed,
        "added": _summarize(doc, added),
        "removed": _summarize(other, removed),
        "modified": _summarize(doc, modified),
        "metrics": {"entities": {"from": len(old), "to": len(cur)},
                    "volume": _vol_delta(other, doc),
                    "area_2d": _area_delta(other, doc)},
    }


def _summarize(doc, ids):
    out = []
    for eid in ids[:50]:
        ent = doc.entities[eid]
        row = {"id": eid, "type": ent["type"], "layer": ent.get("layer")}
        if ent.get("tag"):
            row["tag"] = ent["tag"]
        out.append(row)
    return {"count": len(ids), "entities": out}


def _vol_delta(a, b):
    from .. import shapes

    def total(d):
        v = 0.0
        for ent in d.entities.values():
            if ent["type"] in ("solid", "wall"):
                try:
                    v += shapes.entity_to_manifold(d, ent).volume()
                except CadError:
                    pass
        return round(v, 6)
    return {"from": total(a), "to": total(b)}


def _area_delta(a, b):
    from .. import shapes

    def total(d):
        v = 0.0
        for ent in d.entities.values():
            if ent["type"] in ("circle", "polyline", "spline", "region", "room"):
                try:
                    v += shapes.to_cross_section(d, ent).area()
                except CadError:
                    pass
        return round(v, 6)
    return {"from": total(a), "to": total(b)}
