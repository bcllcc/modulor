"""The integration artifacts must never rot.

- every ```json block in integrations/COOKBOOK.md actually runs
- tool-definitions.json is in sync with the live registry
- the MCP registry manifest matches the released version
"""
import json
import os
import re

import pytest

from modulor import Cad
from modulor.engine import run_batch

ROOT = os.path.join(os.path.dirname(__file__), "..")
COOKBOOK = os.path.join(ROOT, "integrations", "COOKBOOK.md")

_BLOCKS = re.findall(r"```json\n(.*?)```", open(COOKBOOK, encoding="utf-8").read(),
                     re.S)


def test_cookbook_has_recipes():
    assert len(_BLOCKS) >= 8


@pytest.mark.parametrize("i", range(len(_BLOCKS)))
def test_cookbook_recipe_runs(i, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # recipes write relative output files
    # recipe 4 imports a drawing: provide one from the corpus
    src = os.path.join(ROOT, "examples", "out", "studio_plan.dxf")
    (tmp_path / "site_plan.dxf").write_bytes(open(src, "rb").read())

    commands = json.loads(_BLOCKS[i])
    # follow-up fragments (regenerate/restore/diff/find/get) need the doc
    # from the preceding recipe: replay all earlier blocks into one doc
    cad = Cad(str(tmp_path / "doc.json"))
    cad.save()
    standalone = any(c.get("op", "").startswith(("add_", "import_", "recipe"))
                     for c in commands)
    if not standalone:
        for prev in _BLOCKS[:i]:
            try:
                run_batch(cad.doc, json.loads(prev))
            except Exception:
                pass
    results = cad.run(commands)
    assert all(r["ok"] for r in results)
    cad.save()


def test_tool_definitions_in_sync():
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from export_tool_defs import coarse_tool, fine_tools

    stored = json.load(open(os.path.join(ROOT, "integrations",
                                         "tool-definitions.json"),
                            encoding="utf-8"))
    assert stored["coarse"] == [coarse_tool()], \
        "regenerate: python scripts/export_tool_defs.py"
    assert stored["fine"] == fine_tools(), \
        "regenerate: python scripts/export_tool_defs.py"


def test_demo_adapter_works(tmp_path, monkeypatch):
    """The shared adapter under integrations/demos must actually drive the
    kernel — exercised here with the same kind of batch the demo brief
    produces, including the error path the model relies on."""
    sys_path = os.path.join(ROOT, "integrations", "demos")
    import sys
    sys.path.insert(0, sys_path)
    from modulor_tool import TOOL_PARAMETERS, modulor_run

    monkeypatch.chdir(tmp_path)
    out = json.loads(modulor_run("out/demo.json", [
        {"op": "add_wall",
         "path": [[0, 0], [6000, 0], [6000, 4000], [0, 4000], [0, 0]],
         "thickness": 240, "tag": "room"},
        {"op": "add_opening", "wall": {"tags": ["room"]}, "along": 1500,
         "width": 900, "type": "door"},
        {"op": "measure", "kind": "area", "select": {"tags": ["room"]}},
        {"op": "render", "path": "out/demo_plan.png", "mode": "plan",
         "labels": True},
    ]))
    assert out["ok"] and os.path.exists("out/demo_plan.png")
    assert out["results"][2]["value"] > 0

    # stringified commands (some models do this) and structured errors
    out = json.loads(modulor_run("out/demo.json", '[{"op":"validate"}]'))
    assert out["ok"]
    out = json.loads(modulor_run("out/demo.json", [{"op": "nope"}]))
    assert not out["ok"] and "hint" in out["error"]

    assert TOOL_PARAMETERS["required"] == ["doc", "commands"]


def test_demo_projects_compile():
    """Framework demos are real projects; at minimum they must parse."""
    import py_compile
    demos = os.path.join(ROOT, "integrations", "demos")
    checked = 0
    for sub in ("langchain", "autogen", "crewai"):
        main = os.path.join(demos, sub, "main.py")
        py_compile.compile(main, doraise=True)
        assert os.path.exists(os.path.join(demos, sub, "requirements.txt"))
        checked += 1
    assert checked == 3


def test_claude_plugin_manifests():
    """The Claude Code plugin/marketplace manifests stay valid and pinned."""
    from modulor import __version__
    mp = json.load(open(os.path.join(ROOT, ".claude-plugin",
                                     "marketplace.json"), encoding="utf-8"))
    assert mp["name"] == "modulor"
    entry = mp["plugins"][0]
    assert entry["version"] == __version__, \
        "marketplace.json plugin version drifted from the package"
    plugin_dir = os.path.join(ROOT, entry["source"])
    pj = json.load(open(os.path.join(plugin_dir, ".claude-plugin",
                                     "plugin.json"), encoding="utf-8"))
    assert pj["version"] == __version__
    assert os.path.exists(os.path.join(plugin_dir, "skills", "modulor",
                                       "SKILL.md"))
    mcp = json.load(open(os.path.join(plugin_dir, ".mcp.json"),
                         encoding="utf-8"))
    assert mcp["mcpServers"]["modulor"]["command"] == "modulor"


def test_mcp_manifest_version():
    from modulor import __version__
    m = json.load(open(os.path.join(ROOT, "server.json"), encoding="utf-8"))
    assert m["name"] == "io.github.bcllcc/modulor"
    assert m["version"] == __version__, \
        "server.json version drifted from the package"
    assert m["packages"][0]["version"] == __version__
