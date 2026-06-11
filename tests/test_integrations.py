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


def test_mcp_manifest_version():
    from modulor import __version__
    m = json.load(open(os.path.join(ROOT, "server.json"), encoding="utf-8"))
    assert m["name"] == "io.github.bcllcc/modulor"
    assert m["version"] == __version__, \
        "server.json version drifted from the package"
    assert m["packages"][0]["version"] == __version__
