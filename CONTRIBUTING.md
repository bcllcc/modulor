# Contributing to Modulor

Thanks for considering it. This project runs on a small number of hard
rules that keep the API trustworthy for the agents that depend on it.

## Dev setup

```bash
git clone https://github.com/bcllcc/modulor
cd modulor
pip install -e .[dev] -e ./extensions/modulor-mech
pytest tests extensions/modulor-mech/tests -q     # all green before you start
```

Useful entry points: `modulor ops` (the API), `scripts/fuzz.py` (the
behavioral fuzzer), `scripts/bench.py` (scale benchmark),
`modulor serve <doc>` (live viewer while developing).

## The contract workflow (the one rule you must not skip)

The op surface is a frozen contract (`docs/api.json`). If your change
alters any op's params/effects/returns or the error registry:

1. it is a **Standard-level change** — open an RFC issue first
   (template provided) and wait for acceptance;
2. after implementing, run `python scripts/api_dump.py` and
   `python scripts/export_tool_defs.py`, and commit the regenerated
   files **in the same commit** as the code.

CI diffs the live registry against the stored contract; drift fails.

## API laws

New ops must follow the laws in AGENT_GUIDE.md §3.5 (selector naming,
created/modified result keys, effects declaration, 100% param docs and
returns, units-scaled defaults). The conventions tests enforce them.
Domain semantics belong in extensions, not core — see docs/PLUGINS.md
and GOVERNANCE.md §4.

## Quality bar for PRs

- All tests green, including the fuzz slice and the DXF corpus.
- New behavior comes with tests; bug fixes come with a regression test.
- Validate-before-mutate: a failing op must never leave a broken entity
  in the document.
- Errors are `CadError` with a registered code and, where possible, a
  hint that tells an agent how to fix the call.
- Keep kernel dependencies at numpy + manifold3d. No exceptions without
  an RFC.

## Releases (maintainers)

Bump the version in `pyproject.toml`, `modulor/__init__.py`,
`server.json`, `.claude-plugin/marketplace.json` and the plugin manifest
(tests pin them together), re-run the two generator scripts, then push a
`v*` tag — PyPI and the MCP registry publish automatically.

## Conduct

Be kind, be specific, argue about geometry not people.
