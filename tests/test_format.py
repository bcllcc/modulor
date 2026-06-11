"""The document format is a standard: every document the implementation
produces must validate against docs/document.schema.json, and the public
numbers in README must match reality.
"""
import glob
import json
import os
import re

import jsonschema
import pytest

from modulor import Cad

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture(scope="module")
def validator():
    # canonical copy: the one shipped inside the package (used by
    # `modulor check`); docs/ holds a synced copy for browsing
    with open(os.path.join(ROOT, "modulor", "document.schema.json"),
              encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_schema_copies_in_sync():
    with open(os.path.join(ROOT, "modulor", "document.schema.json"),
              encoding="utf-8") as f:
        packaged = f.read()
    with open(os.path.join(ROOT, "docs", "document.schema.json"),
              encoding="utf-8") as f:
        docs_copy = f.read()
    assert packaged == docs_copy, \
        "schema copies diverged — run scripts/api_dump.py to re-sync"


def test_cli_check_command(tmp_path, capsys):
    """`modulor check` is the conformance entry point for any
    implementation's documents."""
    from modulor.cli import main as cli_main

    good = tmp_path / "good.json"
    cad = Cad(str(good))
    cad("add_circle", center=[0, 0], radius=10)
    cad.save()
    assert cli_main(["check", str(good)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["schema"] == "ok"

    bad = tmp_path / "bad.json"
    d = json.loads(json.dumps(cad.doc.to_dict()))
    d["entities"]["e1"]["radius"] = -5  # corrupt geometry + schema breach
    bad.write_text(json.dumps(d), encoding="utf-8")
    assert cli_main(["check", str(bad)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert not out["ok"]
    assert out["geometry_problems"] or out["schema_errors"]


def test_kitchen_sink_document_validates(validator):
    """One of every entity type, serialized, must satisfy the schema."""
    cad = Cad(units="mm")
    cad("set_param", name="bay", value=4000)
    cad("add_level", name="L1", elevation=0, height=3000)
    cad("add_material", name="alu", color="#aab4bd")
    cad("add_line", start=[0, 0], end=[100, 0])
    cad("add_polyline", points=[[0, 0], [50, 0], [50, 30]], closed=False)
    cad("add_spline", closed=True, tag="s",
        points=[[200, 0], [260, 40], [320, 0], [260, -40]])
    cad("add_circle", center=[400, 0], radius=30)
    cad("add_arc", center=[500, 0], radius=40, start_angle=0, end_angle=90)
    cad("add_rect", at=[600, 0], width=80, height=50, tag="r")
    cad("boolean_2d", kind="union", a={"tags": ["r"]})       # region
    cad("add_text", at=[0, 100], text="HELLO", height=20)
    cad("add_dim", p1=[0, 0], p2=[100, 0], offset=-30)
    cad("add_dim_angular", center=[700, 0], p1=[750, 0], p2=[700, 50])
    cad("add_circle", center=[800, 0], radius=25, tag="c2")
    cad("add_dim_radial", of={"tags": ["c2"]}, direction=30)
    cad("add_wall", path=[[0, 200], [500, 200]], thickness=20, tag="w")
    cad("add_opening", wall={"tags": ["w"]}, along=250, width=80)
    cad("add_grid", x=[0, 100, 200], y=[0, 150])
    cad("add_room", name="ROOM", level="L1",
        points=[[0, 300], [100, 300], [100, 400], [0, 400]])
    cad("add_box", at=[900, 0, 0], size=[50, 50, 50], material="alu")
    cad("recipe_set", commands=[
        {"op": "define_param", "name": "bay", "value": 4000},
        {"op": "add_circle", "center": [0, 0], "radius": "bay/10"},
    ])

    blob = json.dumps(cad.doc.to_dict(), allow_nan=False)
    doc_dict = json.loads(blob)
    errors = sorted(validator.iter_errors(doc_dict), key=lambda e: e.json_path)
    assert not errors, "\n".join(
        f"{e.json_path}: {e.message[:140]}" for e in errors[:8])

    types = {e["type"] for e in doc_dict["entities"].values()}
    assert len(types) == 14, f"kitchen sink is missing types: {types}"


def test_example_documents_validate(validator):
    """Every committed example output document conforms to the format."""
    docs = glob.glob(os.path.join(ROOT, "examples", "out", "*.json"))
    checked = 0
    for path in docs:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("format") not in ("modulor/1", "nativecad/1"):
            continue
        errors = list(validator.iter_errors(d))
        assert not errors, f"{os.path.basename(path)}: " + "; ".join(
            f"{e.json_path}: {e.message[:120]}" for e in errors[:5])
        checked += 1
    assert checked >= 3, "expected several example documents in examples/out"


def test_meta_fields_required(tmp_path, capsys):
    """FORMAT.md requires meta.name/created/modified — the schema and
    `modulor check` must enforce it (review finding: meta:{} passed)."""
    from modulor.cli import main as cli_main

    cad = Cad(str(tmp_path / "m.json"))
    cad("add_circle", center=[0, 0], radius=5)
    d = json.loads(json.dumps(cad.doc.to_dict()))
    d["meta"] = {}
    p = tmp_path / "no_meta.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    assert cli_main(["check", str(p)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert any("meta" in e or "name" in e for e in out["schema_errors"])


def test_check_strict_requires_validator(tmp_path, capsys, monkeypatch):
    """--strict is the conformance mode: no validator, no pass."""
    import sys as _sys

    from modulor.cli import main as cli_main

    cad = Cad(str(tmp_path / "s.json"))
    cad("add_circle", center=[0, 0], radius=5)
    cad.save()
    # normal mode degrades gracefully without jsonschema...
    monkeypatch.setitem(_sys.modules, "jsonschema", None)
    assert cli_main(["check", str(tmp_path / "s.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"].startswith("skipped")
    # ...strict mode refuses to bless what it cannot verify
    assert cli_main(["check", str(tmp_path / "s.json"), "--strict"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert "modulor[check]" in out["error"]["hint"]


def test_readme_op_count_is_current():
    """The headline number in README must match the registry — public
    claims are part of the contract too."""
    from modulor.ops import REGISTRY
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        readme = f.read()
    m = re.search(r"(\d+) 个自描述操作", readme)
    assert m, "README lost its op-count headline"
    assert int(m.group(1)) == len(REGISTRY), (
        f"README says {m.group(1)} ops but the registry has "
        f"{len(REGISTRY)} — update README.md")
    # no other stale op-counts hiding anywhere
    for stale in re.findall(r"(\d+) 个(?:自描述 )?op\b", readme):
        assert int(stale) == len(REGISTRY)
