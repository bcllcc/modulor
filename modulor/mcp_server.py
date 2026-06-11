"""Model Context Protocol server over stdio (newline-delimited JSON-RPC 2.0).

Implemented directly on the wire protocol — no SDK dependency. Three tools:

  cad_run     run a batch of ops against a document file (atomic save)
  cad_ops     discover the op API (list all, or details for one op)
  cad_render  render the model to PNG and return it as image content,
              so multimodal agents can visually inspect their work

Document state lives in files; this server is stateless between calls.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile

from . import __version__
from .document import Document
from .engine import BatchError, run_batch
from .errors import CadError
from .ops import describe_op, list_ops

PROTOCOL_FALLBACK = "2024-11-05"

TOOLS = [
    {
        "name": "cad_run",
        "description": (
            "Run Modulor drawing/modeling commands against a document file. "
            "Creates the document if missing; saves only if every command "
            "succeeds. Commands are flat JSON objects like "
            '{"op": "add_wall", "path": [[0,0],[6000,0]], "thickness": 200}. '
            'Discover all ops with the cad_ops tool (or {"op": "help"}).'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc": {"type": "string",
                        "description": "path to the .json document file"},
                "commands": {"type": "array", "items": {"type": "object"},
                             "description": "ordered list of op commands"},
                "units": {"type": "string", "enum": ["mm", "cm", "m", "in", "ft"],
                          "description": "units if the document is created"},
            },
            "required": ["doc", "commands"],
        },
    },
    {
        "name": "cad_ops",
        "description": ("Discover the Modulor op API. Without arguments: "
                        "every op with a one-line summary. With name: full "
                        "parameter docs and an example for that op."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "op name, e.g. 'extrude'"},
            },
        },
    },
    {
        "name": "cad_render",
        "description": ("Render a Modulor document to a PNG image and return "
                        "it for visual inspection. mode 'plan' = 2D drawing, "
                        "'shaded' = 3D view, 'auto' picks for you. camera: "
                        "'iso', 'iso_left', 'top', 'front', 'right', ... or "
                        '{"eye": [x,y,z], "target": [x,y,z], "fov": 45}.'),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc": {"type": "string"},
                "mode": {"type": "string", "enum": ["auto", "plan", "shaded"]},
                "camera": {"description": "named view string or eye/target object"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "select": {"description": "entity selector (default all)"},
                "save_to": {"type": "string",
                            "description": "also keep the PNG at this path"},
            },
            "required": ["doc"],
        },
    },
]


def serve():
    stdin = sys.stdin.buffer
    while True:
        line = stdin.readline()
        if not line:
            break
        line = line.lstrip(b"\xef\xbb\xbf").strip()  # tolerate a UTF-8 BOM
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _send({"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": "parse error"}})
            continue
        _handle(msg)


def _handle(msg: dict):
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        client_ver = params.get("protocolVersion") or PROTOCOL_FALLBACK
        _reply(mid, {
            "protocolVersion": client_ver,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "modulor", "version": __version__},
        })
    elif method in ("notifications/initialized", "initialized"):
        pass  # notification, no response
    elif method == "ping":
        _reply(mid, {})
    elif method == "tools/list":
        _reply(mid, {"tools": TOOLS})
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            _reply(mid, _call_tool(name, args))
        except (CadError, BatchError) as e:
            _reply(mid, _error_content(e.to_dict()))
        except Exception as e:  # never crash the transport
            _reply(mid, _error_content(
                {"code": "internal", "message": f"{type(e).__name__}: {e}"}))
    elif mid is not None:
        _send({"jsonrpc": "2.0", "id": mid,
               "error": {"code": -32601, "message": f"method not found: {method}"}})


def _call_tool(name: str, args: dict) -> dict:
    if name == "cad_run":
        doc = Document.open_or_create(args["doc"], units=args.get("units", "mm"))
        try:
            results = run_batch(doc, args["commands"])
        except BatchError as e:
            return _error_content({**e.to_dict(), "results": e.results,
                                   "saved": False})
        doc.save()
        return _text_content({"ok": True, "results": results,
                              "doc": args["doc"], "saved": True})

    if name == "cad_ops":
        if args.get("name"):
            return _text_content(describe_op(args["name"]))
        return _text_content({"ops": list_ops()})

    if name == "cad_render":
        doc = Document.load(args["doc"])
        save_to = args.get("save_to")
        path = save_to or os.path.join(tempfile.gettempdir(), "modulor_mcp.png")
        cmd = {"op": "render", "path": path}
        for k in ("mode", "camera", "width", "height", "select"):
            if args.get(k) is not None:
                cmd[k] = args[k]
        results = run_batch(doc, [cmd])  # render mutates nothing; no save
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        if not save_to:
            try:
                os.remove(path)
            except OSError:
                pass
        return {"content": [
            {"type": "image", "data": data, "mimeType": "image/png"},
            {"type": "text", "text": json.dumps(results[0], ensure_ascii=False)},
        ]}

    raise CadError("unknown_tool", f"no tool named {name!r}",
                   hint="tools: cad_run, cad_ops, cad_render")


def _text_content(obj) -> dict:
    return {"content": [{"type": "text",
                         "text": json.dumps(obj, ensure_ascii=False)}]}


def _error_content(err: dict) -> dict:
    return {"content": [{"type": "text",
                         "text": json.dumps({"ok": False, "error": err},
                                            ensure_ascii=False)}],
            "isError": True}


def _reply(mid, result: dict):
    if mid is None:
        return
    _send({"jsonrpc": "2.0", "id": mid, "result": result})


def _send(obj: dict):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()
