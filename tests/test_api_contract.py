"""The op API is a frozen contract.

This test diffs the live registry against docs/api.json. If it fails, you
changed the public interface: either revert, or — if the change is
intentional — run `python scripts/api_dump.py` and commit the updated
contract together with the code (and a version bump once we are post-1.0).
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from api_dump import contract  # noqa: E402


def _stored():
    with open(os.path.join(ROOT, "docs", "api.json"), encoding="utf-8") as f:
        return json.load(f)


def test_op_surface_matches_contract():
    live = contract()
    stored = _stored()
    live_ops, stored_ops = live["ops"], stored["ops"]

    missing = sorted(set(stored_ops) - set(live_ops))
    assert not missing, f"ops removed from the registry: {missing}"
    added = sorted(set(live_ops) - set(stored_ops))
    assert not added, (f"new ops not in the contract: {added} — run "
                       "scripts/api_dump.py and commit docs/api.json")

    for name in stored_ops:
        s, l = stored_ops[name], live_ops[name]
        assert l["effects"] == s["effects"], \
            f"{name}: effects changed {s['effects']} -> {l['effects']}"
        s_params, l_params = s["params"], l["params"]
        gone = sorted(set(s_params) - set(l_params))
        assert not gone, f"{name}: params removed: {gone}"
        new = sorted(set(l_params) - set(s_params))
        assert not new, f"{name}: params added without contract update: {new}"
        for pname in s_params:
            assert l_params[pname] == s_params[pname], (
                f"{name}.{pname} changed: "
                f"{s_params[pname]} -> {l_params[pname]}")


def test_conventions_hold():
    """Codified naming conventions — additions must follow them."""
    live = contract()["ops"]
    for name, e in live.items():
        params = e["params"]
        # 1. generic multi-entity selection is always called 'select'
        for bad in ("selection", "entities", "targets"):
            assert bad not in params, f"{name}: use 'select', not '{bad}'"
        # 2. in-place mutators report {modified}; creators report {created}
        if "keep_profile" in params or "keep_profiles" in params:
            raise AssertionError(f"{name}: use the unified 'keep' param")
        # 3. every op declares effects
        assert e["effects"] in ("doc", "files", "none")
        # 4. creator ops are add_* or derivation verbs, all lowercase
        assert name == name.lower()
        # 5. rotational extent is 'angle'; placement direction is
        #    'direction'; creation orientation is 'rotation'
        assert "sweep" not in params, \
            f"{name}: rotational extent should be named 'angle'"


# Every op belongs to exactly one result category. Adding an op means
# adding it here — that is the point: result-shape drift becomes a
# conscious, reviewed decision instead of an accident.
CREATORS = {  # return {created: [ids], ...}
    "add_arc", "add_box", "add_circle", "add_cylinder", "add_dim",
    "add_dim_angular", "add_dim_radial", "add_facade", "add_grid",
    "add_implicit", "add_line", "add_polyline", "add_rect", "add_roof",
    "add_room", "add_sphere", "add_spline", "add_stair", "add_surface",
    "add_text", "add_wall", "array", "boolean_2d", "boolean_3d", "copy",
    "extrude", "import_dxf", "loft", "offset", "project", "revolve",
    "slice", "solidify", "sweep",
}
MUTATORS = {  # return {modified: [ids], ...}
    "add_opening", "chamfer", "deform", "fillet", "move", "rotate",
    "scale", "shell", "smooth", "update",
}
DUAL = {"mirror"}  # {modified} in place, {created} with copy=true
QUERIES = {  # effects=none, return data
    "diff", "doc_info", "find", "get", "help", "list", "list_layers",
    "measure", "params", "program", "snapshots", "validate",
}
FILE_WRITERS = {"export", "render", "snapshot"}
RESOURCE_OPS = {  # named-resource and lifecycle ops with their own shapes
    "add_layer", "add_level", "add_material", "define_param", "delete",
    "doc_new", "recipe_set", "regenerate", "restore", "set_param",
    "set_units",
}


def _core_registry():
    from modulor.ops import REGISTRY
    return {n: e for n, e in REGISTRY.items()
            if e.get("origin", "core") == "core"}


def test_result_categories_cover_everything():
    REGISTRY = _core_registry()
    cats = [CREATORS, MUTATORS, DUAL, QUERIES, FILE_WRITERS, RESOURCE_OPS]
    union = set().union(*cats)
    assert union == set(REGISTRY), (
        f"uncategorized ops: {sorted(set(REGISTRY) - union)}; "
        f"stale entries: {sorted(union - set(REGISTRY))}")
    for i, a in enumerate(cats):
        for b in cats[i + 1:]:
            assert not (a & b), f"ops in two categories: {sorted(a & b)}"


def test_result_declarations_match_category():
    REGISTRY = _core_registry()
    for name in CREATORS:
        ret = REGISTRY[name]["returns"]
        assert "created" in ret, f"{name}: creators must declare 'created'"
        assert "modified" not in ret, f"{name}: creators never return 'modified'"
    for name in MUTATORS:
        ret = REGISTRY[name]["returns"]
        assert "modified" in ret, f"{name}: mutators must declare 'modified'"
        assert "created" not in ret, f"{name}: mutators never return 'created'"
    for name in DUAL:
        ret = REGISTRY[name]["returns"]
        assert "modified" in ret and "created" in ret
    for name in QUERIES:
        assert REGISTRY[name]["effects"] == "none", \
            f"{name}: queries must declare effects=none"
    for name in FILE_WRITERS:
        assert REGISTRY[name]["effects"] == "files"
    for name in RESOURCE_OPS | QUERIES:
        ret = REGISTRY[name]["returns"]
        assert "created:" not in ret and "modified:" not in ret, \
            f"{name}: entity-id keys are reserved for creators/mutators"


def test_result_keys_at_runtime():
    """Spot-check the law holds in actual results, not just declarations."""
    from modulor import Cad
    cad = Cad(units="mm")
    r = cad("add_circle", center=[0, 0], radius=10, tag="c")
    assert "created" in r and "modified" not in r
    r = cad("move", select={"tags": ["c"]}, by=[5, 0])
    assert "modified" in r and "created" not in r
    r = cad("mirror", select={"tags": ["c"]}, p1=[0, 0], p2=[0, 1])
    assert "modified" in r
    r = cad("mirror", select={"tags": ["c"]}, p1=[0, 0], p2=[0, 1], copy=True)
    assert "created" in r


# The complete set of selector-typed parameter names. 'select' is the
# generic one; the rest are role-specific single targets. A new
# selector param must either be called 'select' or be added here with a
# semantic justification.
SELECTOR_PARAM_NAMES = {"select", "a", "b", "wall", "profile",
                        "footprint", "boundary", "of"}


def test_selector_param_names_locked():
    REGISTRY = _core_registry()
    seen = set()
    for name, e in REGISTRY.items():
        for pname, sp in e["params"].items():
            if sp["type"] == "select":
                assert pname in SELECTOR_PARAM_NAMES, (
                    f"{name}.{pname}: selector params must be 'select' or "
                    f"one of the role names {sorted(SELECTOR_PARAM_NAMES)}")
                seen.add(pname)
    stale = SELECTOR_PARAM_NAMES - seen
    assert not stale, f"allowlist entries no longer used: {sorted(stale)}"


def test_json_schema_matches_runtime():
    """Tool-definition schemas must tell the truth about expressions:
    numeric fields accept number|string, integer fields integer|string,
    and runtime-validated enums/required carry through."""
    from modulor.ops import REGISTRY, json_schema
    for name, e in REGISTRY.items():
        js = json_schema(name)
        assert js["type"] == "object"
        for pname, sp in e["params"].items():
            frag = js["properties"][pname]
            if sp["type"] == "number":
                assert frag["type"] == ["number", "string"], f"{name}.{pname}"
            elif sp["type"] == "integer":
                assert frag["type"] == ["integer", "string"], f"{name}.{pname}"
            elif sp["type"] in ("point2", "point3"):
                assert frag["items"]["type"] == ["number", "string"]
            elif sp["type"] == "points":
                assert frag["items"]["items"]["type"] == ["number", "string"]
            if sp["enum"]:
                assert frag["enum"] == sp["enum"], f"{name}.{pname}"
            if sp["type"] in ("number", "integer", "point2", "point3",
                              "points") and sp["doc"]:
                assert "expression" in frag["description"], \
                    f"{name}.{pname}: schema must mention expression support"
            assert (pname in js["required"]) == bool(sp["required"]), \
                f"{name}.{pname}: required mismatch"


def test_every_param_documented():
    """100% parameter documentation — the API is self-describing."""
    REGISTRY = _core_registry()
    missing = [f"{n}.{p}" for n, e in REGISTRY.items()
               for p, sp in e["params"].items() if not sp["doc"].strip()]
    assert not missing, f"params without docs: {missing}"


def test_every_op_declares_returns():
    """Self-describing goes for outputs too: every op declares its
    result shape."""
    REGISTRY = _core_registry()
    missing = [n for n, e in REGISTRY.items() if not e["returns"].strip()]
    assert not missing, f"ops without a returns declaration: {missing}"


def test_every_example_valid():
    """Each op's example must validate against the op's own schema, so the
    documentation can never go stale against the implementation."""
    from modulor.ops import REGISTRY, validate_params

    class _Resolver:
        def resolve(self, v):  # expressions in examples become 1.0
            return 1.0

    for name, e in REGISTRY.items():
        ex = e["example"]
        if not ex:
            continue
        assert ex.get("op") == name, f"{name}: example uses wrong op name"
        body = {k: v for k, v in ex.items() if k != "op"}
        # raises unknown_param/bad_param if the example drifted
        validate_params(name, body, e["params"], _Resolver())


def test_api_md_documents_exactly_the_core():
    """docs/API.md is the Standard's human form: it must contain exactly
    the contract's ops — never locally-installed plugins (regression
    guard for the API.md pollution finding)."""
    import re
    with open(os.path.join(ROOT, "docs", "API.md"), encoding="utf-8") as f:
        md = f.read()
    documented = set(re.findall(r"^## ([a-z][a-z0-9_.]*)$", md, re.M))
    documented.discard("error")  # the '## Error codes' section header
    contract_ops = set(contract()["ops"])
    assert documented == contract_ops, (
        f"API.md drifted: extra={sorted(documented - contract_ops)} "
        f"missing={sorted(contract_ops - documented)} — run "
        "scripts/api_dump.py")


def test_error_codes_registered():
    """The error taxonomy in the contract matches the code registry."""
    from modulor.errors import ERROR_CODES, CadError
    stored = _stored()
    assert stored["error_codes"] == {k: v for k, v in ERROR_CODES.items()}, \
        "error registry changed: re-run scripts/api_dump.py"
    import pytest
    with pytest.raises(ValueError):
        CadError("made_up_code", "x")  # unregistered codes cannot exist
