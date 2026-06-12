"""The shared Modulor adapter every framework demo imports.

This file is unit-tested in Modulor's CI, so the demos' foundation can
never rot. Copy it into your own project freely (MIT).
"""
from __future__ import annotations

import json

from modulor import Cad, CadError

TOOL_NAME = "modulor_run"
TOOL_DESCRIPTION = (
    "Run Modulor CAD commands against a document file. Use it to draw 2D "
    "plans, model 3D solids, measure/validate geometry, render PNG images "
    "and export DXF/SVG/STL/GLB/IFC. `commands` is an ordered list of "
    '{"op": <name>, ...params} objects; the batch is atomic. Discover any '
    'op with [{"op": "help", "name": "<op>"}]. Prefer "tag"-based '
    "selectors; numeric fields accept expressions like 'bay*2'."
)
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "doc": {"type": "string",
                "description": "path to the .json document (created if "
                               "missing)"},
        "commands": {"type": "array",
                     "description": "ordered op commands",
                     "items": {"type": "object"}},
    },
    "required": ["doc", "commands"],
}


def modulor_run(doc: str, commands: list[dict]) -> str:
    """Execute a Modulor command batch; always returns a JSON string the
    model can read (success results or a structured error with a hint)."""
    if isinstance(commands, str):  # some models stringify the array
        try:
            commands = json.loads(commands)
        except json.JSONDecodeError as e:
            return json.dumps({"ok": False, "error": {
                "code": "bad_json", "message": str(e)}})
    cad = Cad(doc)
    try:
        results = cad.run(commands)
    except CadError as e:
        return json.dumps({"ok": False, "error": e.to_dict()},
                          ensure_ascii=False)
    cad.save()
    return json.dumps({"ok": True, "results": results}, ensure_ascii=False)


# The standard brief used by all demos — small enough to run in one or two
# tool calls, rich enough to prove the loop works.
DEMO_TASK = (
    "Create a CAD document at out/demo.json: draw a 6m x 4m room as a "
    "closed wall ring, 240mm thick walls, with a 900mm door on the south "
    "wall. Then measure the wall area, and render a labeled plan to "
    "out/demo_plan.png. Report the area you measured. Units are mm."
)
