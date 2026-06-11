"""Command-line front-end.

Everything reads/writes JSON on stdout so output is machine-parseable;
exit code 0 = success, 1 = structured error, 2 = usage error.

  modulor ops [name]              discover the API
  modulor new DOC [--units mm]    create an empty document
  modulor info DOC                document summary
  modulor run DOC SCRIPT          run a JSON command batch (SCRIPT='-' = stdin)
  modulor op DOC NAME [JSON]      run a single op
  modulor repl DOC                JSON-Lines session over stdin/stdout
  modulor mcp                     MCP stdio server
"""
from __future__ import annotations

import argparse
import io
import json
import sys

from .document import Document
from .engine import BatchError, run_batch
from .errors import CadError
from .ops import describe_op, list_ops


def main(argv=None) -> int:
    # Windows consoles default to legacy encodings; force UTF-8 JSON I/O
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(prog="modulor",
                                 description="Agent-native 2D/3D CAD")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ops = sub.add_parser("ops", help="list ops / describe one op")
    p_ops.add_argument("name", nargs="?", help="op name")

    p_new = sub.add_parser("new", help="create an empty document")
    p_new.add_argument("doc")
    p_new.add_argument("--units", default="mm")

    p_info = sub.add_parser("info", help="document summary")
    p_info.add_argument("doc")

    p_chk = sub.add_parser("check",
                           help="validate a document file against the "
                                "modulor/1 format (structure + geometry; "
                                "full JSON Schema if jsonschema is installed)")
    p_chk.add_argument("doc")
    p_chk.add_argument("--strict", action="store_true",
                       help="conformance mode: fail (instead of skipping) "
                            "when the jsonschema package is unavailable")

    p_run = sub.add_parser("run", help="run a JSON command batch against a doc")
    p_run.add_argument("doc")
    p_run.add_argument("script", help="JSON file with a command array, or '-'")
    p_run.add_argument("--units", default="mm", help="units if doc is created")
    p_run.add_argument("--as-recipe", action="store_true",
                       help="store the script as the document's recipe and "
                            "regenerate from it (parametric workflow)")
    p_run.add_argument("--pretty", action="store_true")

    p_op = sub.add_parser("op", help="run a single op")
    p_op.add_argument("doc")
    p_op.add_argument("name")
    p_op.add_argument("params", nargs="?", default="{}",
                      help='op params as JSON, e.g. {"start":[0,0],"end":[1,0]}')
    p_op.add_argument("--units", default="mm")
    p_op.add_argument("--pretty", action="store_true")

    p_repl = sub.add_parser("repl", help="JSON-Lines session (one batch per line)")
    p_repl.add_argument("doc")
    p_repl.add_argument("--units", default="mm")

    p_srv = sub.add_parser("serve",
                           help="read-only browser viewer that live-follows "
                                "the document as agents edit it")
    p_srv.add_argument("doc")
    p_srv.add_argument("--port", type=int, default=8400)
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--no-open", action="store_true",
                       help="don't launch a browser")

    sub.add_parser("mcp", help="serve the Model Context Protocol over stdio")

    args = ap.parse_args(argv)

    try:
        if args.cmd == "ops":
            if args.name:
                _emit(describe_op(args.name))
            else:
                _emit({"ops": list_ops(),
                       "usage": "modulor ops <name> for parameter details"})
            return 0
        if args.cmd == "new":
            doc = Document(units=args.units)
            doc.save(args.doc)
            _emit({"ok": True, "doc": args.doc, "units": doc.units})
            return 0
        if args.cmd == "info":
            doc = Document.load(args.doc)
            results = run_batch(doc, [{"op": "doc_info"}])
            _emit(results[0])
            return 0
        if args.cmd == "check":
            return _cmd_check(args)
        if args.cmd == "run":
            return _cmd_run(args)
        if args.cmd == "op":
            return _cmd_op(args)
        if args.cmd == "repl":
            return _cmd_repl(args)
        if args.cmd == "serve":
            from .viewer.server import serve as serve_viewer
            serve_viewer(args.doc, host=args.host, port=args.port,
                         open_browser=not args.no_open)
            return 0
        if args.cmd == "mcp":
            from .mcp_server import serve
            serve()
            return 0
    except CadError as e:
        _emit({"ok": False, "error": e.to_dict()})
        return 1
    except FileNotFoundError as e:
        _emit({"ok": False, "error": {"code": "file_not_found", "message": str(e)}})
        return 1
    except json.JSONDecodeError as e:
        _emit({"ok": False, "error": {"code": "bad_json",
                                      "message": f"invalid JSON: {e}"}})
        return 1
    return 2


def _cmd_check(args) -> int:
    """Conformance check for modulor/1 documents — usable against files
    written by ANY implementation, not just this one.

    Three layers: structural load, geometric validation (the 'validate'
    op), and — when the optional jsonschema package is available — strict
    validation against the packaged document.schema.json.
    """
    with open(args.doc, "r", encoding="utf-8") as f:
        raw = json.load(f)
    doc = Document.from_dict(raw)  # structural: raises bad_format

    problems = run_batch(doc, [{"op": "validate"}])[0]["problems"]

    schema_status = "skipped (pip install modulor[check] to enable)"
    schema_errors: list[str] = []
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is None and args.strict:
        _emit({"ok": False, "doc": args.doc,
               "error": {"code": "bad_format",
                         "message": "--strict requires the jsonschema package "
                                    "for full conformance validation",
                         "hint": "pip install modulor[check]"}})
        return 1
    if jsonschema is not None:
        import os as _os
        schema_path = _os.path.join(_os.path.dirname(__file__),
                                    "document.schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        validator = jsonschema.Draft202012Validator(schema)
        schema_errors = [f"{e.json_path}: {e.message[:160]}"
                         for e in validator.iter_errors(raw)][:20]
        schema_status = "ok" if not schema_errors else "failed"

    ok = not problems and not schema_errors
    _emit({"ok": ok, "doc": args.doc,
           "format": raw.get("format"), "units": doc.units,
           "entities": len(doc.entities),
           "geometry_problems": problems,
           "schema": schema_status,
           "schema_errors": schema_errors})
    return 0 if ok else 1


def _cmd_run(args) -> int:
    if args.script == "-":
        commands = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    else:
        with open(args.script, "r", encoding="utf-8-sig") as f:
            commands = json.load(f)
    doc = Document.open_or_create(args.doc, units=args.units)
    if getattr(args, "as_recipe", False):
        if isinstance(commands, dict):
            commands = [commands]
        commands = [{"op": "recipe_set", "commands": commands, "run": True}]
    try:
        results = run_batch(doc, commands)
    except BatchError as e:
        _emit({"ok": False, "error": e.to_dict(), "results": e.results,
               "doc": args.doc, "saved": False}, args.pretty)
        return 1
    doc.save()
    _emit({"ok": True, "results": results, "doc": args.doc, "saved": True},
          args.pretty)
    return 0


def _cmd_op(args) -> int:
    params = json.loads(args.params)
    if not isinstance(params, dict):
        raise CadError("bad_json", "params must be a JSON object")
    doc = Document.open_or_create(args.doc, units=args.units)
    try:
        results = run_batch(doc, [{"op": args.name, **params}])
    except BatchError as e:
        _emit({"ok": False, "error": e.to_dict(), "doc": args.doc,
               "saved": False}, args.pretty)
        return 1
    doc.save()
    _emit({**results[0], "doc": args.doc, "saved": True}, args.pretty)
    return 0


def _cmd_repl(args) -> int:
    """One JSON command (or array) per input line -> one JSON result line.

    The document is saved after every successful line; a failed line is
    rolled back by reloading the last saved state, so each line is atomic.
    """
    doc = Document.open_or_create(args.doc, units=args.units)
    doc.save()
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8-sig")
    _emit({"ok": True, "ready": True, "doc": args.doc,
           "hint": 'one JSON command or array per line; {"op":"help"} lists ops'})
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        if line in ("exit", "quit"):
            break
        try:
            commands = json.loads(line)
            results = run_batch(doc, commands)
            doc.save()
            _emit({"ok": True, "results": results, "saved": True})
        except json.JSONDecodeError as e:
            _emit({"ok": False, "error": {"code": "bad_json",
                                          "message": f"invalid JSON: {e}"}})
        except BatchError as e:
            doc = Document.load(args.doc)  # roll back this line
            _emit({"ok": False, "error": e.to_dict(), "results": e.results,
                   "saved": False})
    return 0


def _emit(obj, pretty: bool = False):
    print(json.dumps(obj, ensure_ascii=False,
                     indent=2 if pretty else None))
    sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
