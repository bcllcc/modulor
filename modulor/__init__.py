"""Modulor — agent-native 2D drafting + 3D modeling.

No GUI. The entire tool is a set of JSON commands ("ops") applied to a
JSON document, reachable four ways:

  CLI batch     modulor run model.json script.json
  CLI pipe      modulor repl model.json        (JSON Lines in/out)
  MCP server    modulor mcp                    (for MCP-speaking agents)
  Python        from modulor import Cad

>>> cad = Cad("house.json", units="mm")
>>> cad("add_wall", path=[[0, 0], [6000, 0]], thickness=200)
{'ok': True, 'op': 'add_wall', 'created': ['e1'], 'length': 6000.0}
>>> cad("render", path="plan.png")
>>> cad.save()
"""
from .document import Document
from .engine import BatchError, execute, run_batch
from .errors import CadError

__version__ = "0.6.0"
__all__ = ["Cad", "Document", "CadError", "BatchError",
           "execute", "run_batch", "__version__"]


class Cad:
    """Convenience wrapper for Python-side agents and scripts."""

    def __init__(self, path: str | None = None, units: str = "mm"):
        if path:
            self.doc = Document.open_or_create(path, units=units)
        else:
            self.doc = Document(units=units)

    def __call__(self, op: str, **params) -> dict:
        return execute(self.doc, {"op": op, **params})

    def run(self, commands) -> list[dict]:
        return run_batch(self.doc, commands)

    def save(self, path: str | None = None):
        self.doc.save(path)
        return self.doc.path
