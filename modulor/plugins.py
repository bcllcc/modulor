"""The extension mechanism: add domain ops to Modulor without forking.

A plugin is a Python package that declares an entry point in the
``modulor.plugins`` group and exposes a ``register(api)`` function:

    # pyproject.toml
    [project.entry-points."modulor.plugins"]
    mech = "modulor_mech"

    # modulor_mech/__init__.py
    def register(api):
        @api.op("gear", doc="...", params={...}, example={...},
                returns="{created: [id]}")
        def gear(doc, p):
            ...

Rules (enforced, not advisory):

- every plugin op lives in the plugin's namespace: the entry-point name
  becomes the prefix, so the op above is callable as ``mech.gear``;
- plugin ops obey the same API laws as core ops (see
  :func:`check_laws`, which plugin test suites should call);
- plugin ops appear in ``help`` / ``modulor ops`` / MCP discovery like
  any other op, marked with their origin;
- the frozen core contract (docs/api.json) covers core ops only — a
  plugin ships and versions its own surface.

Core scope rule (GOVERNANCE.md): deterministic geometry and protocol
only. Domain semantics belong here, in extensions.
"""
from __future__ import annotations

import re

from .errors import CadError
from .ops import P, REGISTRY, op as _core_op

_NAME_RE = re.compile(r"[a-z][a-z0-9_]*$")
_loaded: dict[str, str] = {}   # namespace -> module name
_load_errors: dict[str, str] = {}


class PluginAPI:
    """What a plugin's ``register(api)`` receives. The namespace comes
    from the entry-point name and cannot be escaped."""

    #: parameter spec helpers, identical to core ops
    P = P

    def __init__(self, namespace: str):
        if not _NAME_RE.match(namespace):
            raise CadError("bad_param",
                           f"plugin namespace {namespace!r} must be "
                           "lowercase [a-z][a-z0-9_]*")
        self.namespace = namespace

    def op(self, name: str, doc: str, params: dict,
           example: dict | None = None, returns: str = "",
           effects: str = "doc"):
        if not _NAME_RE.match(name):
            raise CadError("bad_param",
                           f"op name {name!r} must be lowercase "
                           "[a-z][a-z0-9_]*")
        full = f"{self.namespace}.{name}"
        if full in REGISTRY:
            raise CadError("bad_param", f"op {full!r} is already registered")
        deco = _core_op(full, doc=doc, params=params, example=example,
                        returns=returns, effects=effects)

        def wrap(fn):
            out = deco(fn)
            REGISTRY[full]["origin"] = self.namespace
            return out
        return wrap


def load_plugins() -> dict:
    """Discover and register all installed plugins (idempotent).

    A broken plugin never breaks Modulor: its error is recorded and the
    rest of the system works; see :func:`plugin_status`.
    """
    from importlib.metadata import entry_points
    for ep in entry_points(group="modulor.plugins"):
        if ep.name in _loaded or ep.name in _load_errors:
            continue
        try:
            module = ep.load()
            register = getattr(module, "register")
            register(PluginAPI(ep.name))
            _loaded[ep.name] = ep.value
        except Exception as e:  # isolation: a bad plugin only hurts itself
            _load_errors[ep.name] = f"{type(e).__name__}: {e}"
    return dict(_loaded)


def plugin_status() -> dict:
    return {"loaded": dict(_loaded), "errors": dict(_load_errors)}


# ----------------------------------------------------------------- laws

SELECTOR_PARAM_NAMES = {"select", "a", "b", "wall", "profile",
                        "footprint", "boundary", "of"}


def check_laws(namespace: str) -> list[str]:
    """Verify a plugin's ops against the Modulor API laws. Returns a list
    of violations (empty = compliant). Call this from your plugin's test
    suite:

        assert not check_laws("mech")
    """
    problems = []
    ops = {n: e for n, e in REGISTRY.items()
           if e.get("origin") == namespace}
    if not ops:
        return [f"no ops registered under namespace {namespace!r}"]
    for name, e in ops.items():
        if e["effects"] not in ("doc", "files", "none"):
            problems.append(f"{name}: invalid effects {e['effects']!r}")
        if not e["returns"].strip():
            problems.append(f"{name}: missing returns declaration")
        if not e["doc"].strip():
            problems.append(f"{name}: missing doc")
        if e["example"] is not None and e["example"].get("op") != name:
            problems.append(f"{name}: example uses wrong op name")
        creates = "created" in e["returns"]
        mutates = "modified" in e["returns"]
        if creates and mutates:
            problems.append(f"{name}: returns may declare created OR "
                            "modified, not both")
        for pname, sp in e["params"].items():
            if not sp["doc"].strip():
                problems.append(f"{name}.{pname}: missing param doc")
            if sp["type"] == "select" and pname not in SELECTOR_PARAM_NAMES:
                problems.append(
                    f"{name}.{pname}: selector params must be 'select' or "
                    f"one of {sorted(SELECTOR_PARAM_NAMES)}")
            if pname == "sweep":
                problems.append(f"{name}: rotational extent is 'angle', "
                                "not 'sweep'")
    return problems
