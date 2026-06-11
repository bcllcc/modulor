"""Structured errors. Every failure an agent can hit carries a stable code,
a human-readable message, and (where possible) a hint about how to fix the
call. Codes come from the closed registry below — it is part of the API
contract (docs/api.json), so agents can branch on them safely.
"""
from __future__ import annotations

# The complete error taxonomy. Adding a code here is an API change:
# re-run scripts/api_dump.py and commit the contract with it.
ERROR_CODES: dict[str, str] = {
    # --- request shape
    "bad_command":   "the command/batch is not shaped like {'op': ..., ...}",
    "unknown_op":    "no op with that name (hint suggests close matches)",
    "unknown_param": "the op has no such parameter (hint suggests close matches)",
    "missing_param": "a required parameter was not given",
    "bad_param":     "a parameter has the wrong type, value or range",
    "bad_json":      "input text is not valid JSON",
    # --- selection & targets
    "bad_selector":  "the selector object/string cannot be interpreted",
    "empty_selection": "the selector matched no entities",
    "bad_target":    "selection resolved to the wrong count or kind of entity",
    "bad_type":      "this entity type does not support the operation",
    "not_found":     "no entity/material/level/snapshot with that name",
    # --- geometry
    "degenerate":    "the geometry would be invalid (zero/negative size, "
                     "self-defeating input)",
    "not_closed":    "an open curve was used where a closed area is needed",
    "empty_result":  "the operation produced no geometry (e.g. non-overlapping "
                     "booleans)",
    "over_budget":   "the request exceeds a resource budget (resolution, "
                     "counts); the hint says which knob to turn",
    # --- expressions & parametrics
    "bad_expr":      "a parameter expression failed to parse or evaluate",
    "recipe_error":  "no recipe stored, recipe recursion, or a recipe "
                     "command failed (message says which)",
    # --- files & environment
    "bad_format":    "unsupported or malformed file format",
    "file_not_found": "the input file does not exist",
    "no_path":       "the document has no file path yet (save it first)",
    "unknown_tool":  "MCP: no tool with that name",
    # --- catch-all
    "internal":      "unexpected internal failure (please report)",
}


class CadError(Exception):
    def __init__(self, code: str, message: str, hint: str | None = None):
        if code not in ERROR_CODES:
            raise ValueError(f"unregistered error code {code!r} — add it to "
                             "ERROR_CODES (it is part of the API contract)")
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.hint:
            d["hint"] = self.hint
        return d
