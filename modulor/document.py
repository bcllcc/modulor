"""Document model: a JSON-serializable scene of layers, materials and entities.

The whole document is plain data (dicts/lists) so it round-trips losslessly
through JSON and is trivially inspectable by agents. Entity ids are "e1",
"e2", ... and never reused within a document.
"""
from __future__ import annotations

import json
import os
import time

from .errors import CadError

FORMAT = "modulor/1"
# documents written before the rename remain readable forever
LEGACY_FORMATS = ("nativecad/1",)
UNITS = ("mm", "cm", "m", "in", "ft")

DEFAULT_LAYER = {"color": "#222222", "visible": True, "line_width": 1.0}
DEFAULT_MATERIAL = {"color": "#9aa0a6", "metallic": 0.0, "roughness": 0.8}

ENTITY_TYPES_2D = ("line", "polyline", "spline", "circle", "arc", "region",
                   "text", "dim", "dim_angular", "dim_radial", "wall",
                   "grid", "room")
ENTITY_TYPES_3D = ("solid",)
ENTITY_TYPES = ENTITY_TYPES_2D + ENTITY_TYPES_3D


class Document:
    def __init__(self, units: str = "mm", name: str = "untitled"):
        if units not in UNITS:
            raise CadError("bad_param", f"unknown units {units!r}",
                           hint=f"use one of {UNITS}")
        self.units = units
        self.meta = {"name": name, "created": _now(), "modified": _now()}
        self.layers: dict[str, dict] = {"0": dict(DEFAULT_LAYER)}
        self.materials: dict[str, dict] = {"default": dict(DEFAULT_MATERIAL)}
        self.entities: dict[str, dict] = {}
        self.params: dict[str, float] = {}     # named design parameters
        self.levels: dict[str, dict] = {}      # name -> {elevation, height}
        self.recipe: list[dict] = []           # the program that built this doc
        self._counter = 0
        self.path: str | None = None  # where this doc lives on disk, if anywhere

    # ------------------------------------------------------------- expressions

    def resolve(self, value):
        """Number params accept expression strings: 'bay*3+200',
        'level("L2")', 'grid_x("B")'. Returns a float."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if not isinstance(value, str):
            raise CadError("bad_param", f"expected number or expression, "
                                        f"got {value!r}")
        from .expr import eval_expr

        def level(name, _key="elevation"):
            if name not in self.levels:
                raise CadError("not_found", f"no level named {name!r}",
                               hint=f"levels: {sorted(self.levels)}")
            return float(self.levels[name]["elevation"])

        def level_top(name):
            lv = self.levels.get(name)
            if lv is None:
                raise CadError("not_found", f"no level named {name!r}")
            return float(lv["elevation"]) + float(lv.get("height", 0.0))

        def _grid_lookup(axis, label):
            label = str(label)
            for ent in self.entities.values():
                if ent.get("type") != "grid":
                    continue
                labels = ent[f"{axis}_labels"]
                coords = ent[f"{axis}s"]
                if label in labels:
                    return float(coords[labels.index(label)])
            raise CadError("not_found", f"no grid line labeled {label!r} "
                                        f"on the {axis} axis")

        out = eval_expr(value, extra_names=dict(self.params),
                        extra_funcs={"level": level, "level_top": level_top,
                                     "grid_x": lambda s: _grid_lookup("x", s),
                                     "grid_y": lambda s: _grid_lookup("y", s)})
        import math
        if not math.isfinite(out):
            raise CadError("bad_expr",
                           f"expression {value!r} produced a non-finite number")
        return out

    # ------------------------------------------------------------- ids

    def new_id(self) -> str:
        self._counter += 1
        return f"e{self._counter}"

    # ------------------------------------------------------------- entities

    def add_entity(self, etype: str, data: dict, layer: str = "0",
                   tag: str | None = None) -> str:
        if etype not in ENTITY_TYPES:
            raise CadError("bad_type", f"unknown entity type {etype!r}")
        if layer not in self.layers:
            # auto-create layers on first use: agents shouldn't have to
            # pre-declare every layer
            self.layers[layer] = dict(DEFAULT_LAYER)
        eid = self.new_id()
        ent = {"type": etype, "layer": layer, **data}
        if tag:
            ent["tag"] = tag
        self.entities[eid] = ent
        return eid

    def get_entity(self, eid: str) -> dict:
        if not isinstance(eid, str):
            raise CadError("bad_selector",
                           f"entity ids are strings, got {eid!r}")
        if eid not in self.entities:
            # ids are generated lowercase ("e7") but renders display them in a
            # caps-only stroke font; accept "E7" so reading an image works
            low = eid.lower() if isinstance(eid, str) else eid
            if low in self.entities:
                return self.entities[low]
            raise CadError("not_found", f"entity {eid!r} does not exist",
                           hint="use the 'list' op to see existing ids")
        return self.entities[eid]

    def delete_entities(self, ids) -> int:
        n = 0
        for eid in ids:
            if eid in self.entities:
                del self.entities[eid]
                n += 1
        return n

    # ------------------------------------------------------------- selectors

    def select(self, sel) -> list[str]:
        """Resolve a selector to entity ids (in creation order).

        Selector forms:
          "all"                      -> every entity
          "e12"                      -> single id
          ["e1", "e2"]               -> list of ids (errors on unknown id)
          {"ids": [...], "tags": [...], "layers": [...], "types": [...]}
                                     -> AND of the given filters
        """
        if sel is None or sel == "all":
            return list(self.entities.keys())
        norm = lambda e: e if e in self.entities else \
            (e.lower() if isinstance(e, str) else e)  # noqa: E731
        if isinstance(sel, str):
            self.get_entity(sel)
            return [norm(sel)]
        if isinstance(sel, list):
            for eid in sel:
                self.get_entity(eid)
            return [norm(e) for e in sel]
        if isinstance(sel, dict):
            ids = sel.get("ids")
            if ids:
                ids = [norm(e) for e in ids]
            tags = sel.get("tags") or ([sel["tag"]] if sel.get("tag") else None)
            layers = sel.get("layers") or ([sel["layer"]] if sel.get("layer") else None)
            types = sel.get("types") or ([sel["type"]] if sel.get("type") else None)
            if ids:
                for eid in ids:
                    self.get_entity(eid)
            out = []
            for eid, ent in self.entities.items():
                if ids and eid not in ids:
                    continue
                if tags and ent.get("tag") not in tags:
                    continue
                if layers and ent.get("layer") not in layers:
                    continue
                if types and ent.get("type") not in types:
                    continue
                out.append(eid)
            return out
        raise CadError("bad_selector", f"cannot interpret selector {sel!r}",
                       hint='use "all", an id, a list of ids, or '
                            '{"layers": [...], "types": [...], "tags": [...]}')

    # ------------------------------------------------------------- io

    def to_dict(self) -> dict:
        return {
            "format": FORMAT,
            "units": self.units,
            "meta": self.meta,
            "counter": self._counter,
            "layers": self.layers,
            "materials": self.materials,
            "params": self.params,
            "levels": self.levels,
            "recipe": self.recipe,
            "entities": self.entities,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        if d.get("format") not in (FORMAT, *LEGACY_FORMATS):
            raise CadError("bad_format", f"not a {FORMAT} document")
        doc = cls(units=d.get("units", "mm"))
        doc.meta = d.get("meta", doc.meta)
        doc._counter = int(d.get("counter", 0))
        doc.layers = d.get("layers", doc.layers)
        doc.materials = d.get("materials", doc.materials)
        doc.params = d.get("params", {})
        doc.levels = d.get("levels", {})
        doc.recipe = d.get("recipe", [])
        doc.entities = d.get("entities", {})
        return doc

    def save(self, path: str | None = None):
        path = path or self.path
        if not path:
            raise CadError("no_path", "document has no file path")
        self.meta["modified"] = _now()
        d = os.path.dirname(os.path.abspath(path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
        self.path = path

    @classmethod
    def load(cls, path: str) -> "Document":
        with open(path, "r", encoding="utf-8") as f:
            doc = cls.from_dict(json.load(f))
        doc.path = path
        return doc

    @classmethod
    def open_or_create(cls, path: str, units: str = "mm") -> "Document":
        if os.path.exists(path):
            return cls.load(path)
        doc = cls(units=units, name=os.path.splitext(os.path.basename(path))[0])
        doc.path = path
        return doc


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
