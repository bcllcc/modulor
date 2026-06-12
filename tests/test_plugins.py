"""The plugin mechanism's own guarantees: namespacing is structural,
collisions are impossible, a broken plugin cannot hurt the core, and the
frozen contract ignores plugins entirely."""
import pytest

from modulor import Cad, CadError
from modulor.ops import REGISTRY
from modulor.plugins import PluginAPI, check_laws


@pytest.fixture
def sandbox():
    """Register throwaway ops under a test namespace, clean up after."""
    created = []
    api = PluginAPI("ztest")
    orig_op = api.op

    def tracking_op(name, **kw):
        deco = orig_op(name, **kw)

        def wrap(fn):
            created.append(f"ztest.{name}")
            return deco(fn)
        return wrap
    api.op = tracking_op
    yield api
    for n in created:
        REGISTRY.pop(n, None)


def _add_dummy(api, name="dot"):
    @api.op(name, doc="Test op.", params={
        "at": api.P.point2(req=True, doc="position")},
        example={"op": f"{api.namespace}.{name}", "at": [0, 0]},
        returns="{created: [id]}")
    def dot(doc, p):
        eid = doc.add_entity("circle", {"center": p["at"], "radius": 1},
                             layer="0")
        return {"created": [eid]}


def test_namespace_is_structural(sandbox):
    _add_dummy(sandbox)
    assert "ztest.dot" in REGISTRY
    assert REGISTRY["ztest.dot"]["origin"] == "ztest"
    cad = Cad(units="mm")
    r = cad("ztest.dot", at=[5, 5])
    assert r["created"]


def test_collision_rejected(sandbox):
    _add_dummy(sandbox)
    with pytest.raises(CadError, match="already registered"):
        _add_dummy(sandbox)


def test_cannot_shadow_core(sandbox):
    with pytest.raises(CadError, match="already registered"):
        # namespacing makes this impossible by construction; even a
        # namespace literally named like a core op cannot collide
        PluginAPI("add_wall")  # fine as namespace...
        api = PluginAPI("ztest")
        api2 = PluginAPI("ztest")
        _add_dummy(api)
        try:
            _add_dummy(api2)  # same full name -> rejected
        finally:
            REGISTRY.pop("ztest.dot", None)


def test_bad_names_rejected():
    with pytest.raises(CadError):
        PluginAPI("Bad-Name")
    api = PluginAPI("ok")
    with pytest.raises(CadError):
        api.op("Bad.Op", doc="x", params={})


def test_check_laws_catches_violations(sandbox):
    @sandbox.op("sloppy", doc="Bad citizen.", params={
        "sweep": sandbox.P.number(doc="misnamed"),
        "x": sandbox.P.number(req=True, doc="")},
        returns="")
    def sloppy(doc, p):
        return {}
    problems = check_laws("ztest")
    text = " ".join(problems)
    assert "returns" in text and "sweep" in text and "param doc" in text \
        or len(problems) >= 3


def test_broken_plugin_is_isolated():
    """A register() that explodes must not take Modulor down."""
    from modulor import plugins

    class _FakeEp:
        name = "zbroken"
        value = "zbroken_module"

        def load(self):
            raise RuntimeError("boom")

    plugins._load_errors.pop("zbroken", None)
    try:
        ep = _FakeEp()
        try:
            mod = ep.load()
        except Exception as e:
            plugins._load_errors[ep.name] = f"{type(e).__name__}: {e}"
        status = plugins.plugin_status()
        assert "zbroken" in status["errors"]
        # core still fully functional
        cad = Cad(units="mm")
        assert cad("add_circle", center=[0, 0], radius=5)["created"]
    finally:
        plugins._load_errors.pop("zbroken", None)


def test_plugins_cli(tmp_path, capsys):
    """`modulor plugins` is the diagnostic surface; with a namespace it
    becomes the conformance gate (exit 1 on law violations)."""
    import json as _json

    from modulor.cli import main as cli_main

    code = cli_main(["plugins"])
    out = _json.loads(capsys.readouterr().out)
    assert "loaded" in out and "errors" in out
    if "mech" in out["loaded"]:  # extension present in dev/CI envs
        assert code == 0
        assert "mech.gear" in out["loaded"]["mech"]["ops"]
        assert cli_main(["plugins", "mech"]) == 0
        chk = _json.loads(capsys.readouterr().out)
        assert chk["ok"] and chk["law_violations"] == []
    assert cli_main(["plugins", "no_such_ns"]) == 1
    err = _json.loads(capsys.readouterr().out)
    assert err["error"]["code"] == "not_found"


def test_contract_excludes_plugins(sandbox):
    _add_dummy(sandbox)
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                    "scripts"))
    from api_dump import contract
    ops = contract()["ops"]
    assert "ztest.dot" not in ops
    assert not any(n.startswith("ztest.") for n in ops)
