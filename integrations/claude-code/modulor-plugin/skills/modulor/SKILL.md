---
name: modulor
description: 2D drafting + 3D modeling via Modulor (agent-native CAD). Use when the user asks to draw floor plans, model buildings or parts, produce DXF/SVG drawings, STL/GLB meshes, IFC BIM models, or to import and modify existing DXF drawings. Requires `pip install modulor`.
---

# Modulor — agent-native CAD

You drive CAD through JSON commands. One document = one `.json` file.

## Setup check

```bash
modulor ops >/dev/null || pip install modulor
```

## Core workflow

1. **Run command batches** (atomic — all succeed or nothing is saved):

```bash
modulor run model.json - <<'EOF'
[{"op":"add_wall","path":[[0,0],[8000,0],[8000,5000],[0,5000],[0,0]],
  "thickness":240,"height":2900,"tag":"ext"},
 {"op":"add_opening","wall":{"tags":["ext"]},"along":1500,"width":1000,"type":"door"},
 {"op":"render","path":"check.png","mode":"plan"}]
EOF
```

2. **Look at what you made**: `render` writes a PNG — read it. Add
   `"labels": true` to print entity ids on the image.
3. **Verify numerically**: `{"op":"measure","kind":"area","select":...}`,
   `{"op":"validate"}`, `{"op":"find","at":[x,y],"radius":r}`.
4. **Export**: `.dxf` `.svg` (drawings) · `.glb` `.stl` `.obj` (meshes) ·
   `.ifc` (semantic BIM for Revit) — via `{"op":"export","path":"out.ifc"}`.

## Rules that prevent 90% of mistakes

- Discover, don't guess: `modulor ops <name>` gives every param + example.
- Prefer `tag` + `{"tags":[...]}` selectors over hardcoded ids — booleans
  consume entities and ids go stale.
- Numeric fields accept expressions: `"bay*3"`, `"level_top('L2')"`,
  `"grid_x('B')"` (params via `define_param`, levels via `add_level`,
  grids via `add_grid`).
- Z is up; angles are degrees CCW; units default to mm.
- Errors are structured JSON with a `hint` — read it, fix, resend the batch.
- Parametric design: store the script with
  `{"op":"recipe_set","commands":[...],"run":true}`, then
  `{"op":"regenerate","params":{"bay":5000}}` rebuilds everything
  coordinated.
- Before risky edits: `{"op":"snapshot","name":"safe"}`; roll back with
  `restore`; compare options with `{"op":"diff","against":"safe"}`.

## Taking over existing drawings

`{"op":"import_dxf","path":"site.dxf"}` reads real-world DXF (blocks,
hatches, GBK text). Then render with labels, inspect with `find`, rebuild
semantics with `add_wall`/`add_room` where needed.

## Showing the human

Suggest they run `modulor serve model.json` — a read-only browser viewer
that live-follows the document while you work.

Full reference: run `modulor ops`, or read AGENT_GUIDE.md in the Modulor
repository (github.com/bcllcc/modulor).
