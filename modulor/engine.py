"""Batch executor: the single entry point every front-end (CLI, REPL, MCP,
Python API) goes through.

Commands are flat JSON objects: {"op": "<name>", ...params}. A batch is a
list of commands, executed in order. Batches are atomic at the persistence
layer: callers only save the document if the whole batch succeeded.
"""
from __future__ import annotations

from .document import Document
from .errors import CadError
from .ops import REGISTRY, validate_params

# importing these modules registers all ops
from .ops import (arch, blocks, doc_ops, draw2d, export_ops,  # noqa: F401
                  model3d, param_ops, query, transform)

# installed extensions register theirs (isolated: a broken plugin only
# disables itself — see modulor.plugins.plugin_status)
from .plugins import load_plugins as _load_plugins

_load_plugins()


class BatchError(CadError):
    def __init__(self, index: int, opname: str, err: CadError, results: list):
        super().__init__(err.code, err.message, err.hint)
        self.index = index
        self.opname = opname
        self.results = results

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["at_command"] = self.index
        d["at_op"] = self.opname
        return d


def execute(doc: Document, command: dict) -> dict:
    if not isinstance(command, dict):
        raise CadError("bad_command",
                       f"a command must be an object, got {type(command).__name__}",
                       hint='shape: {"op": "add_line", "start": [0,0], "end": [1,0]}')
    cmd = dict(command)
    opname = cmd.pop("op", None)
    if not opname or not isinstance(opname, str):
        raise CadError("bad_command",
                       'command needs an "op" key with the op name as a string',
                       hint='use {"op": "help"} to list available ops')
    if opname not in REGISTRY:
        from .ops import describe_op
        describe_op(opname)  # raises with a did-you-mean hint
    entry = REGISTRY[opname]
    params = validate_params(opname, cmd, entry["params"], doc)
    try:
        result = entry["fn"](doc, params)
    except CadError:
        raise
    except Exception as e:  # invariant: callers always get structured errors
        raise CadError("internal", f"{type(e).__name__}: {e}",
                       hint="this is a bug in modulor — please report "
                            "the command that caused it") from e
    return {"ok": True, "op": opname, **(result or {})}


def run_batch(doc: Document, commands) -> list[dict]:
    if isinstance(commands, dict):
        commands = [commands]
    if not isinstance(commands, list):
        raise CadError("bad_command", "expected a command object or a list of them")
    results = []
    for i, cmd in enumerate(commands):
        try:
            results.append(execute(doc, cmd))
        except CadError as e:
            raise BatchError(i, cmd.get("op", "?") if isinstance(cmd, dict) else "?",
                             e, results) from e
        except Exception as e:  # kernel/internal errors, still structured
            err = CadError("internal", f"{type(e).__name__}: {e}")
            raise BatchError(i, cmd.get("op", "?") if isinstance(cmd, dict) else "?",
                             err, results) from e
    return results
