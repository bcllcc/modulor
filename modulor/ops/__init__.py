"""Operation registry.

Every capability of Modulor is an *op*: a named command taking a flat JSON
object and returning a JSON result. Ops are self-describing (typed params,
docs, examples), so agents can discover the full API at runtime via the
`help` op / `modulor ops` instead of reading documentation.
"""
from __future__ import annotations

import difflib

from ..errors import CadError

REGISTRY: dict[str, dict] = {}


# ---------------------------------------------------------------- param specs

def _spec(ptype, req=False, default=None, doc="", enum=None):
    return {"type": ptype, "required": req, "default": default,
            "doc": doc, "enum": enum}


class P:
    @staticmethod
    def number(req=False, default=None, doc=""):
        return _spec("number", req, default, doc)

    @staticmethod
    def integer(req=False, default=None, doc=""):
        return _spec("integer", req, default, doc)

    @staticmethod
    def string(req=False, default=None, doc=""):
        return _spec("string", req, default, doc)

    @staticmethod
    def boolean(req=False, default=None, doc=""):
        return _spec("boolean", req, default, doc)

    @staticmethod
    def enum(values, req=False, default=None, doc=""):
        return _spec("string", req, default, doc, enum=list(values))

    @staticmethod
    def point2(req=False, default=None, doc="point [x, y]"):
        return _spec("point2", req, default, doc)

    @staticmethod
    def point3(req=False, default=None, doc="point [x, y, z]"):
        return _spec("point3", req, default, doc)

    @staticmethod
    def points(req=False, default=None, doc="list of [x, y] points"):
        return _spec("points", req, default, doc)

    @staticmethod
    def select(req=False, default=None,
               doc='selector: "all", an id like "e3", a list of ids, or '
                   '{"layers": [...], "types": [...], "tags": [...]}'):
        return _spec("select", req, default, doc)

    @staticmethod
    def layer(doc="target layer (created on first use)"):
        return _spec("string", False, None, doc)

    @staticmethod
    def material(doc="material name (define with add_material)"):
        return _spec("string", False, None, doc)

    @staticmethod
    def tag(doc="optional label for later selection"):
        return _spec("string", False, None, doc)

    @staticmethod
    def obj(req=False, default=None, doc="object"):
        return _spec("object", req, default, doc)

    @staticmethod
    def array(req=False, default=None, doc="array"):
        return _spec("array", req, default, doc)


# world-coordinate sanity bound: 1e9 mm = a thousand kilometers. Values
# beyond this are bugs (or JSON NaN/Infinity), never geometry — and they
# stay far inside the geometry kernel's fixed-point coordinate range.
MAX_MAGNITUDE = 1e9


def _finite(v: float, name: str) -> float:
    import math
    if not math.isfinite(v):
        raise CadError("bad_param", f"param {name!r} is not a finite number")
    if abs(v) > MAX_MAGNITUDE:
        raise CadError("bad_param",
                       f"param {name!r} = {v} exceeds the coordinate bound "
                       f"of {MAX_MAGNITUDE:g}")
    return v


def _scalar(value, resolve, name):
    """A number, or an expression string when a resolver is available."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _finite(float(value), name)
    if isinstance(value, str) and resolve is not None:
        return _finite(resolve(value), name)
    raise CadError("bad_param",
                   f"param {name!r} should be a number"
                   + (" or an expression string like 'bay*2'"
                      if resolve else "") + f", got {value!r}")


def _check_value(name: str, value, spec, resolve=None):
    t = spec["type"]
    ok = True
    if value is None:
        return None
    if t == "number":
        value = _scalar(value, resolve, name)
    elif t == "integer":
        if isinstance(value, str) and resolve is not None:
            v = _finite(resolve(value), name)
            if abs(v - round(v)) > 1e-9:
                raise CadError("bad_param",
                               f"param {name!r} needs an integer, "
                               f"expression gave {v}")
            value = int(round(v))
        ok = isinstance(value, int) and not isinstance(value, bool)
        if ok and abs(value) > MAX_MAGNITUDE:
            raise CadError("bad_param",
                           f"param {name!r} = {value} is out of range")
    elif t == "string":
        ok = isinstance(value, str)
        if ok and spec["enum"] and value not in spec["enum"]:
            raise CadError("bad_param",
                           f"param {name!r}: {value!r} is not one of {spec['enum']}")
    elif t == "boolean":
        ok = isinstance(value, bool)
    elif t == "point2":
        ok = isinstance(value, (list, tuple)) and len(value) == 2
        if ok:
            value = [_scalar(v, resolve, name) for v in value]
    elif t == "point3":
        ok = isinstance(value, (list, tuple)) and len(value) in (2, 3)
        if ok:
            value = [_scalar(v, resolve, name) for v in value]
            if len(value) == 2:
                value.append(0.0)
    elif t == "points":
        ok = (isinstance(value, (list, tuple)) and
              all(isinstance(p, (list, tuple)) and len(p) == 2 for p in value))
        if ok:
            value = [[_scalar(p[0], resolve, name),
                      _scalar(p[1], resolve, name)] for p in value]
    # select / object / array are validated downstream
    if not ok:
        raise CadError("bad_param",
                       f"param {name!r} should be a {t}, got {value!r}")
    return value


def validate_params(opname: str, params: dict, spec: dict, doc=None) -> dict:
    resolve = doc.resolve if doc is not None else None
    out = {}
    for key in params:
        if key not in spec:
            close = difflib.get_close_matches(key, spec.keys(), n=1)
            hint = f"did you mean {close[0]!r}?" if close else \
                f"valid params: {sorted(spec.keys())}"
            raise CadError("unknown_param",
                           f"op {opname!r} has no param {key!r}", hint=hint)
    for key, sp in spec.items():
        if key in params and params[key] is not None:
            out[key] = _check_value(key, params[key], sp, resolve)
        elif sp["required"]:
            raise CadError("missing_param",
                           f"op {opname!r} requires param {key!r} ({sp['doc']})",
                           hint=f'see: {{"op": "help", "name": "{opname}"}}')
        else:
            out[key] = sp["default"]
    return out


# ---------------------------------------------------------------- registration

def op(name: str, doc: str, params: dict, example: dict | None = None,
       returns: str = "", effects: str = "doc"):
    """Register an op. `effects` declares what it touches:
    'doc' mutates the document, 'files' writes files but leaves the
    document unchanged, 'none' is a pure query (always safe to call)."""
    if effects not in ("doc", "files", "none"):
        raise ValueError(f"bad effects {effects!r} for op {name!r}")
    def deco(fn):
        REGISTRY[name] = {"fn": fn, "doc": doc, "params": params,
                          "example": example, "returns": returns,
                          "effects": effects}
        return fn
    return deco


def describe_op(name: str) -> dict:
    if name not in REGISTRY:
        close = difflib.get_close_matches(name, REGISTRY.keys(), n=2)
        hint = f"did you mean {' or '.join(repr(c) for c in close)}?" if close \
            else "use the 'help' op to list everything"
        raise CadError("unknown_op", f"no op named {name!r}", hint=hint)
    e = REGISTRY[name]
    params = {}
    for k, sp in e["params"].items():
        d = {"type": sp["type"], "doc": sp["doc"]}
        if sp["required"]:
            d["required"] = True
        if sp["default"] is not None:
            d["default"] = sp["default"]
        if sp["enum"]:
            d["enum"] = sp["enum"]
        params[k] = d
    out = {"op": name, "doc": e["doc"], "effects": e["effects"],
           "params": params}
    if e["returns"]:
        out["returns"] = e["returns"]
    if e["example"]:
        out["example"] = e["example"]
    return out


def list_ops() -> list[dict]:
    return [{"op": n, "doc": e["doc"], "effects": e["effects"]}
            for n, e in sorted(REGISTRY.items())]


# JSON-schema fragments for MCP tool definitions. Numeric fields accept
# either a number or a parameter-expression string ("bay*2",
# "level_top('L2')") — the schema must say so, or agents exposed to it as
# a tool definition will believe expressions are invalid.
_NUM = {"type": ["number", "string"],
        "description": "number, or expression string like 'bay*2'"}
_SCHEMA_MAP = {
    "number": dict(_NUM),
    "integer": {"type": ["integer", "string"],
                "description": "integer, or expression string like 'cols-1'"},
    "string": {"type": "string"},
    "boolean": {"type": "boolean"},
    "point2": {"type": "array", "items": {"type": ["number", "string"]},
               "minItems": 2, "maxItems": 2},
    "point3": {"type": "array", "items": {"type": ["number", "string"]},
               "minItems": 2, "maxItems": 3},
    "points": {"type": "array",
               "items": {"type": "array",
                         "items": {"type": ["number", "string"]},
                         "minItems": 2, "maxItems": 2}},
    "select": {},
    "object": {"type": "object"},
    "array": {"type": "array"},
}


def json_schema(name: str) -> dict:
    e = REGISTRY[name]
    props, required = {}, []
    for k, sp in e["params"].items():
        frag = dict(_SCHEMA_MAP.get(sp["type"], {}))
        if sp["doc"]:
            note = (" (number or expression string like 'bay*2')"
                    if sp["type"] in ("number", "integer", "point2",
                                      "point3", "points") else "")
            frag["description"] = sp["doc"] + note
        if sp["enum"]:
            frag["enum"] = sp["enum"]
        props[k] = frag
        if sp["required"]:
            required.append(k)
    return {"type": "object", "properties": props, "required": required}
