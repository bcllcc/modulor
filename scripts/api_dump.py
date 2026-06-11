"""Generate the API contract artifacts from the live op registry.

  docs/api.json  - machine-readable contract; the conformance test
                   (tests/test_api_contract.py) diffs the registry against
                   it, so accidental interface changes fail CI. To make an
                   INTENTIONAL change: edit the ops, re-run this script,
                   and commit both together.
  docs/API.md    - the same surface for humans.

Run:  python scripts/api_dump.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modulor import __version__  # noqa: E402
from modulor.errors import ERROR_CODES  # noqa: E402
from modulor.ops import REGISTRY  # noqa: E402


def contract() -> dict:
    ops = {}
    for name, e in sorted(REGISTRY.items()):
        params = {}
        for pname, sp in e["params"].items():
            d = {"type": sp["type"]}
            if sp["required"]:
                d["required"] = True
            if sp["default"] is not None:
                d["default"] = sp["default"]
            if sp["enum"]:
                d["enum"] = sp["enum"]
            params[pname] = d
        ops[name] = {"effects": e["effects"], "params": params,
                     "returns": e["returns"]}
    return {"contract": "modulor-ops/1", "version": __version__,
            "op_count": len(ops), "ops": ops,
            "error_codes": dict(sorted(ERROR_CODES.items()))}


def markdown(c: dict) -> str:
    lines = [
        "# Modulor op API",
        "",
        f"{c['op_count']} ops · contract `{c['contract']}` · "
        f"generated from v{c['version']} — do not edit by hand, run "
        "`python scripts/api_dump.py`.",
        "",
        "`effects`: **doc** mutates the document · **files** writes files, "
        "document untouched · **none** pure query.",
        "",
        "## Error codes",
        "",
        "Every failure carries one of these stable codes (plus a message "
        "and, usually, a hint):",
        "",
        "| code | meaning |",
        "|---|---|",
        *(f"| `{k}` | {v} |" for k, v in sorted(ERROR_CODES.items())),
        "",
    ]
    for name in sorted(REGISTRY):
        e = REGISTRY[name]
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"*effects: {e['effects']}*  ")
        lines.append(e["doc"])
        lines.append("")
        if e["params"]:
            lines.append("| param | type | required | default | notes |")
            lines.append("|---|---|---|---|---|")
            for pname, sp in e["params"].items():
                req = "yes" if sp["required"] else ""
                dflt = "" if sp["default"] is None else \
                    f"`{json.dumps(sp['default'])}`"
                notes = sp["doc"] or ""
                if sp["enum"]:
                    notes = (notes + " " if notes else "") + \
                        f"one of {sp['enum']}"
                lines.append(f"| `{pname}` | {sp['type']} | {req} | {dflt} "
                             f"| {notes} |")
            lines.append("")
        if e["returns"]:
            lines.append(f"**returns** `{e['returns']}`")
            lines.append("")
        if e["example"]:
            lines.append("```json")
            lines.append(json.dumps(e["example"], ensure_ascii=False))
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def main():
    root = os.path.join(os.path.dirname(__file__), "..")
    docs = os.path.join(root, "docs")
    os.makedirs(docs, exist_ok=True)
    c = contract()
    with open(os.path.join(docs, "api.json"), "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1, sort_keys=True)
    with open(os.path.join(docs, "API.md"), "w", encoding="utf-8") as f:
        f.write(markdown(c))
    # the canonical document schema lives in the package (shipped in the
    # wheel for `modulor check`); keep the docs/ copy in sync
    src = os.path.join(root, "modulor", "document.schema.json")
    with open(src, encoding="utf-8") as f:
        schema = f.read()
    with open(os.path.join(docs, "document.schema.json"), "w",
              encoding="utf-8") as f:
        f.write(schema)
    print(f"wrote docs/api.json + docs/API.md ({c['op_count']} ops) "
          "+ synced document.schema.json")


if __name__ == "__main__":
    main()
