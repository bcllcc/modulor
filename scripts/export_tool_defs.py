"""Generate function-calling tool definitions from the op registry.

Output: integrations/tool-definitions.json — OpenAI tools format, accepted
by GPT, Kimi, Qwen, DeepSeek and every OpenAI-compatible agent runtime.
Two integration styles are supported by the same file:

  coarse (recommended): expose ONE tool, `modulor_run`, that takes a list
  of op commands — agents discover ops via the embedded catalog;
  fine: expose every op as its own tool (71 tools) for runtimes that
  prefer flat tool lists.

Regenerate together with the contract: python scripts/export_tool_defs.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modulor import __version__  # noqa: E402
from modulor.ops import REGISTRY, json_schema  # noqa: E402


def _core_items():
    return [(n, e) for n, e in sorted(REGISTRY.items())
            if e.get("origin", "core") == "core"]


def coarse_tool() -> dict:
    catalog = "; ".join(f"{n}: {e['doc'].split('.')[0]}"
                        for n, e in _core_items())
    return {
        "type": "function",
        "function": {
            "name": "modulor_run",
            "description": (
                "Run Modulor CAD commands against a document file (2D "
                "drafting + 3D modeling; exports DXF/SVG/GLB/STL/IFC; "
                "renders PNG). Commands are executed atomically in order; "
                "each is {\"op\": <name>, ...params}. Use "
                "{\"op\":\"help\",\"name\":<op>} to inspect any op. "
                "Available ops — " + catalog),
            "parameters": {
                "type": "object",
                "properties": {
                    "doc": {"type": "string",
                            "description": "path to the .json document "
                                           "(created if missing)"},
                    "commands": {
                        "type": "array",
                        "description": "ordered op commands",
                        "items": {"type": "object",
                                  "properties": {"op": {"type": "string"}},
                                  "required": ["op"]},
                    },
                },
                "required": ["doc", "commands"],
            },
        },
    }


def fine_tools() -> list[dict]:
    tools = []
    for name, e in _core_items():
        schema = json_schema(name)
        schema["properties"]["doc"] = {
            "type": "string",
            "description": "path to the .json document (created if missing)"}
        schema["required"] = ["doc"] + schema.get("required", [])
        tools.append({
            "type": "function",
            "function": {
                "name": f"modulor_{name}",
                "description": (e["doc"] + f" [effects: {e['effects']}]")[:1024],
                "parameters": schema,
            },
        })
    return tools


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "integrations")
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "generator": f"modulor {__version__}",
        "contract": "modulor-ops/1",
        "usage": ("Pick ONE style. coarse: a single modulor_run tool "
                  "(recommended; smallest prompt overhead). fine: one tool "
                  "per op. Execute calls by running "
                  "`modulor run <doc> -` with the commands JSON on stdin, "
                  "or via the Python API (modulor.Cad)."),
        "coarse": [coarse_tool()],
        "fine": fine_tools(),
    }
    path = os.path.join(out_dir, "tool-definitions.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"wrote integrations/tool-definitions.json "
          f"({len(payload['fine'])} fine tools + 1 coarse)")


if __name__ == "__main__":
    main()
