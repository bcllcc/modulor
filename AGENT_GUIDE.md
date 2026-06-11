# Modulor — Agent Guide

You are an agent. This document is everything you need to drive Modulor,
a 2D drafting + 3D modeling tool with **no GUI**: the entire tool surface is
JSON commands ("ops") applied to a JSON document file.

## 1. How to call it

Pick whichever channel fits your harness. All four run the same engine.

**One-shot CLI** (best for scripted workflows):

```
modulor run model.json script.json     # script.json = JSON array of commands
modulor run model.json -               # read the command array from stdin
modulor op model.json add_box "{""size"": [100, 60, 40]}"
```

**Pipe / REPL** (best for long interactive sessions — one JSON command or
array per line in, one JSON result line out, document auto-saved per line):

```
modulor repl model.json
```

**MCP server** (best if you speak Model Context Protocol):

```
modulor mcp
```

Tools: `cad_run` (execute commands), `cad_ops` (discover API),
`cad_render` (returns a PNG *image* you can look at).

**Python**:

```python
from modulor import Cad
cad = Cad("model.json", units="mm")
cad("add_wall", path=[[0, 0], [6000, 0]], thickness=200, tag="south")
cad.run([{"op": "render", "path": "check.png"}])
cad.save()
```

**Showing your work to a human**: suggest they run `modulor serve model.json`
— a read-only browser viewer that live-follows the document file. You keep
editing through any channel above; their page updates automatically. There is
nothing for you to call there; it has no write endpoints.

## 2. Discover the API at runtime — do not guess

```
modulor ops              # every op, one line each
modulor ops add_wall     # full params, types, defaults, example
```

The full surface is also in [docs/API.md](docs/API.md) (generated) and
machine-readable in [docs/api.json](docs/api.json) — that file is the
frozen contract; a test fails if the implementation drifts from it.

or in-band: `{"op": "help"}` and `{"op": "help", "name": "add_wall"}`.

Every error is structured and actionable:

```json
{"ok": false, "error": {"code": "unknown_op", "message": "no op named 'add_circl'",
                        "hint": "did you mean 'add_circle' or 'add_arc'?",
                        "at_command": 3, "at_op": "add_circl"}}
```

Error `code`s come from a closed, documented registry (22 codes — see the
table in docs/API.md), so you can branch on them safely. Two worth knowing:
`empty_selection` means your selector matched nothing (mutating ops always
tell you instead of silently no-op'ing); `over_budget` means you asked for
unbounded work (the hint says which knob to turn).

## 3. Core model

- **Document** = one JSON file. Layers, materials, entities, units. Create
  with `modulor new model.json --units mm` or just run commands at a
  nonexistent path (it is created).
- **Batches are atomic**: if command N fails, nothing is saved; the error
  tells you which command and why. Fix and resend the whole batch.
- **Ids** are assigned sequentially (`e1`, `e2`, ...) and returned in
  `created`. **Prefer tags**: pass `"tag": "plate"` when creating, then select
  with `{"tags": ["plate"]}`. Tags survive booleans; hardcoded ids go stale.
- **Selectors** (any param named `select` / `a` / `b` / `wall`):
  `"all"` | `"e3"` | `["e1", "e2"]` |
  `{"tags": [...], "layers": [...], "types": [...], "ids": [...]}` (AND-ed).
- **Entity types**: `line, polyline, circle, arc, region, text, dim, wall`
  (2D) and `solid` (3D). Walls are both: double lines + openings in plan,
  real volumes in 3D.

## 3.5 API laws (every op obeys these — additions must too)

- **Selection**: the generic "which entities" param is always `select`.
  Role-specific single targets keep semantic names (`wall`, `profile`,
  `footprint`, `boundary`, `of`) and accept the same selector syntax.
- **Results**: creators return `created: [ids]`; in-place mutators return
  `modified: [ids]`; pure queries return data. No other id-key names exist.
- **Effects**: every op declares `effects` — `doc` (mutates the document),
  `files` (writes files only: render/export/snapshot), `none` (pure query,
  always safe). Shown in `help` and docs/api.json.
- **Angles**: `angle` = rotation amount or rotational extent (rotate,
  revolve, polar array, deform twist amount); `rotation` = an entity's
  orientation at creation (rect, text); `direction` = which way a generated
  thing points (stair run, roof ridge, dim leader). All degrees, CCW.
- **Placement**: `at` = anchor point; `center` = geometric center of round
  things; `start`/`end` = a segment's ends; `points` = a closed/open
  boundary; `path` = a line to travel along; `along` = scalar distance
  along a path; `z` = base elevation.
- **Consumption**: boolean inputs are consumed unless `keep: true`;
  profile-driven generators (extrude/revolve/loft/sweep) keep inputs unless
  `keep: false`. One param name: `keep`.
- **Defaults** scale with document units (mm-equivalents), so the same
  script reads sensibly in mm or meters.

## 4. Conventions (memorize these)

- Z is up. 2D drawing happens in the XY plane (a floor plan seen from above).
- Angles are **degrees, CCW from +X**.
- Units default to `mm`; everything (defaults included) scales with units.
- `add_dim` offset: + places the dimension line left of p1->p2, − right.
- Wall paths are centerlines. A path whose last point repeats the first is a
  **closed ring**; `smooth: true` splines the path (curved walls).
- `add_opening` positions are **distance along the centerline** to the
  opening's center. Door defaults: sill 0, head 2100 mm-eq. Window: 900/2400.
- `revolve` spins a profile around a vertical axis at `axis_point`:
  profile x = distance from axis, profile y = resulting z.
- 2D booleans need closed shapes (circle / closed polyline / closed spline /
  region / wall). Booleans **consume** inputs unless `keep: true`.
- `loft` sections go bottom-up at increasing z; set `divisions: 8-16` to get
  flowing surfaces instead of ruled facets.
- `sweep` centers the profile on its own centroid and carries it along the
  path with minimal twist; profile x/y map to path normal/binormal.
- `add_implicit`: the solid is where the expression is **positive**; use
  `smin/smax(a, b, k)` for organic blends. Rendered labels are CAPS — ids
  are case-insensitive on lookup, so typing `E7` for `e7` works.

## 5. The feedback loop — verify, don't assume

You can *see* and *measure* everything you make:

| need | op |
|---|---|
| what exists? | `list` (one line per entity), `get` (full geometry) |
| what's *there*? | `find` at=[x,y] radius=… or bbox=… — spatial lookup, sorted by distance |
| is it sane? | `validate` (degenerate geometry, broken refs) |
| how big? | `measure` kind=distance/length/area/volume/bbox |
| what does it look like? | `render` -> PNG (`mode: plan` or `shaded`, cameras `iso/top/front/...` or `{"eye": ..., "target": ...}`) |
| which entity is which on the image? | `render` with `labels: true` — ids/tags are drawn at each entity |
| about to do something risky? | `snapshot` name=… → try → `restore` if it went wrong (`snapshots` lists them) |

A good session: build → `validate` → `measure` what matters → `render`
(labels on if unsure) → look at the image → fix → export.

## 6. Output formats

`export` infers from the extension:
`.svg` `.dxf` (2D drawing: walls, dims, text, true arcs) ·
`.obj` `.stl` `.glb` (3D meshes with materials; GLB is meters/Y-up) ·
`.png` (rendered image) · `.json` (document copy).

## 6.5 Parametric design (the document is data + recipe)

Any numeric field accepts an expression string: `"bay*3"`,
`"level_top('L2')"`, `"grid_x('B')+600"`. Parameters come from
`define_param`/`set_param`; levels from `add_level`; grid intersections
from `add_grid`.

Store the generating commands as the document's **recipe** and the design
becomes regenerable:

```json
{"op": "recipe_set", "run": true, "commands": [
  {"op": "define_param", "name": "bay", "value": 4000},
  {"op": "add_grid", "x": {"start": 0, "count": 5, "spacing": "bay"},
   "y": {"start": 0, "count": 3, "spacing": "bay*1.2"}},
  {"op": "add_cylinder", "at": [0, 0, 0], "radius": 180, "height": 14000,
   "tag": "col"},
  {"op": "array", "select": {"tags": ["col"]}, "kind": "grid",
   "nx": 5, "ny": 3, "dx": "bay", "dy": "bay*1.2"}
]}
```

Then *"change the bay to 5m"* is exactly one call —
`{"op": "regenerate", "params": {"bay": 5000}}` — and the whole model
rebuilds coordinated. CLI shortcut: `modulor run doc.json script.json
--as-recipe`. Design options: `snapshot` before, `diff against=...` after.

## 7. Op catalog (one-liners)

**Document** doc_new, doc_info, set_units, add_layer, list_layers,
add_material, list, get, update, delete, help, validate, measure, find,
snapshot, restore, snapshots, diff.

**Parametrics** define_param, set_param, params, add_level, recipe_set,
regenerate.

**Architecture** add_grid (axes + bubbles, grid_x/grid_y lookups),
add_room + program (area schedule), add_roof (flat/shed/gable),
add_stair (comfort-rule treads), add_facade (mullion grid + glass),
add_surface (doubly-curved slab from z = f(x, y)).

**2D** add_line, add_polyline, add_spline, add_rect, add_circle, add_arc,
add_text, add_dim, add_dim_angular, add_dim_radial, add_wall, add_opening,
offset, boolean_2d, fillet, chamfer.

**Transforms (2D + 3D)** move, copy, rotate, scale, mirror, array (grid/polar).

**3D** add_box, add_cylinder, add_sphere, extrude, revolve, boolean_3d,
solidify (wall→solid), slice (3D→2D section), project (plan/elevation
outline, axis=z/x/y), shell (hollow).

**Freeform 3D** loft (skin through sections), sweep (profile along path),
deform (twist/taper/bend), add_implicit (solid from a math expression),
smooth (subdivision smoothing).

**I/O** export (svg/dxf/obj/stl/glb/png/json), render, import_dxf.

## 8. Worked example (floor plan → 3D → files)

```json
[
  {"op": "add_wall", "path": [[0,0],[8000,0],[8000,5000],[0,5000],[0,0]],
   "thickness": 240, "height": 2900, "tag": "exterior"},
  {"op": "add_opening", "wall": {"tags": ["exterior"]}, "along": 1500,
   "width": 1000, "type": "door"},
  {"op": "add_opening", "wall": {"tags": ["exterior"]}, "along": 6200,
   "width": 1800, "type": "window"},
  {"op": "add_dim", "p1": [0,0], "p2": [8000,0], "offset": -800},
  {"op": "validate"},
  {"op": "render", "path": "plan.png", "mode": "plan"},
  {"op": "render", "path": "iso.png", "mode": "shaded", "camera": "iso"},
  {"op": "export", "path": "drawing.dxf"},
  {"op": "export", "path": "model.glb"}
]
```

More: [examples/floorplan.json](examples/floorplan.json) (architecture),
[examples/bracket.json](examples/bracket.json) (mechanical: rounded plate,
hole array, slot, boss — 2D booleans → extrude → 3D booleans → STL/GLB).
