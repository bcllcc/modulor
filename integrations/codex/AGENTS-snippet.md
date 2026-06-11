# Modulor snippet for AGENTS.md

Append this section to your project's `AGENTS.md` (read by Codex and other
AGENTS.md-aware agents):

---

## CAD / geometry tasks — use Modulor

This project uses [Modulor](https://github.com/bcllcc/modulor)
(`pip install modulor`) for 2D drafting and 3D modeling. It is a CLI/JSON
tool — no GUI.

- Run command batches: `modulor run <doc.json> <script.json>` where the
  script is a JSON array of `{"op": ..., ...params}` commands. Atomic:
  a failed command means nothing is saved.
- Discover ops with `modulor ops` / `modulor ops <name>` — do not guess
  parameters. Errors return JSON with a `hint`; follow it.
- After modeling, verify: render a PNG and inspect it
  (`{"op":"render","path":"x.png","labels":true}`), and check numbers
  with `measure`/`validate`.
- Use `tag`s for selection; numeric fields accept parameter expressions
  (`"bay*2"`); `recipe_set` + `regenerate` give parametric rebuilds.
- Export `.dxf`/`.svg` drawings, `.stl`/`.glb` meshes, `.ifc` BIM models.
  Import existing drawings with `import_dxf`.
