# The Modulor document format — `modulor/1`

One JSON file is the complete model: geometry, layers, materials, design
parameters and the program that generated it. The format is the second
half of the Modulor standard (the op API in [API.md](API.md) is the
first): anything that can read and write this file can interoperate with
every tool built on Modulor.

Machine-validatable schema: [document.schema.json](document.schema.json)
(JSON Schema 2020-12). The test suite validates every example document
against it, and `modulor check FILE --strict` is the conformance
checker for documents from any implementation
(`pip install modulor[check]` for full schema validation).

## Design rules

1. **Strict JSON.** No `NaN`, no `Infinity`, no comments. A document must
   round-trip through any standards-compliant JSON parser.
2. **Plain data.** No references between entities except by id string; no
   computed values stored that can be derived (a wall stores its
   centerline, never its footprint polygon or mesh).
3. **Diffable.** Ids are stable and never reused (`counter` only grows),
   so two versions of a document diff cleanly line by line.
4. **Self-contained.** Solids embed their meshes; there are no sidecar
   files and no external resources.

## Top level

| field | meaning |
|---|---|
| `format` | `"modulor/1"` (readers must also accept the pre-rename legacy id `"nativecad/1"`) |
| `units` | `mm` `cm` `m` `in` `ft` — interpretation of every coordinate |
| `meta` | `name`, `created`, `modified` (ISO-8601 local) — all three required; writers may add extra fields |
| `counter` | last issued entity number; `e<counter>` was the latest id |
| `layers` | name → `{color, visible, line_width}` |
| `materials` | name → `{color, metallic, roughness}` (PBR, 0..1) |
| `params` | name → number — named design parameters |
| `levels` | name → `{elevation, height?}` — building storeys |
| `recipe` | the op-command list that generates this model (may be empty) |
| `entities` | id (`e1`, `e2`, ...) → entity object |

## Conventions (normative)

- **Axes**: Z is up. 2D entities live in the XY plane (a plan seen from
  above). Exporters convert (glTF output is Y-up, meters).
- **Angles**: degrees, counter-clockwise, measured from +X.
- **Winding**: closed contours bounding area are stored CCW; holes
  (inside `region` contours) are CW. Fill is the positive/non-zero rule.
- **Solids**: watertight manifold triangle meshes, CCW winding seen from
  outside, vertices rounded to 5 decimals.
- **Coordinates**: finite, |value| ≤ 1e9. Writers must reject anything
  else (this also keeps geometry kernels in their safe range).
- **Ids**: lowercase `e<N>`, assigned sequentially, never reused within a
  document. Readers should treat ids case-insensitively.

## Entities

Fourteen types. Every entity has `type`, `layer` and an optional `tag`
(the stable, human/agent-given handle that survives regeneration).

| type | geometry fields | notes |
|---|---|---|
| `line` | `start`, `end` | |
| `polyline` | `points[]`, `closed` | closed ⇒ bounds area |
| `spline` | `points[]`, `closed`, `samples` | centripetal Catmull-Rom *through* the points; `samples` = segments between points |
| `circle` | `center`, `radius` | |
| `arc` | `center`, `radius`, `start_angle`, `end_angle` | CCW from start to end |
| `region` | `contours[][]` | boolean results; CCW outers + CW holes |
| `text` | `at`, `text`, `height`, `rotation` | `at` is baseline-left |
| `dim` | `p1`, `p2`, `offset`, `text?` | aligned dimension; value measured live, `text` overrides |
| `dim_angular` | `center`, `p1`, `p2`, `radius`, `text?` | CCW angle at center between the two rays |
| `dim_radial` | `center`, `radius`, `direction`, `text?` | leader at `direction` degrees |
| `wall` | `path[]`, `thickness`, `openings[]`, `height?`, `material?` | parametric: plan footprint and 3D body are **derived**, never stored. `path` last point == first ⇒ closed ring. Opening: `{at, width, type, sill?, head?}`, `at` = distance along centerline |
| `grid` | `xs[]`, `ys[]`, `x_labels[]`, `y_labels[]` | structural axes; labels feed `grid_x('B')` expressions |
| `room` | `name`, `points[]`, `kind`, `level?` | program annotation; area derived live |
| `solid` | `mesh{vertices, triangles}`, `material?` | the only 3D-native type |

Defaults that are *not* stored (derived at use time, scaled to document
units as mm-equivalents): wall height 3000, door sill 0 / head 2100,
window sill 900 / head 2400.

## Parameters, levels and the recipe

`params`, `levels` and grid entities feed the **expression language**:
any numeric field in any op command may be a string expression such as
`"bay*3"`, `"level_top('L2')"`, `"grid_x('B')+600"` (see API.md, ops
`define_param`/`set_param`/`add_level`/`add_grid`).

`recipe` stores op commands verbatim — including unresolved expression
strings. `regenerate` clears the entities and replays the recipe against
the current `params`, which is how a design stays coordinated when a
parameter changes. The recipe is the document's *design intent*; entities
are merely its current evaluation.

A reader that ignores `params`/`levels`/`recipe` still sees a complete,
correct static model.

## Versioning policy

- `modulor/1` may gain **optional** fields and new entity types in
  minor releases; readers must ignore unknown optional fields and may
  skip unknown entity types (counting them, never silently mutating).
- Any change to existing fields' meaning is a new major format
  (`modulor/2`) — writers will provide a migration.
- The schema file is versioned together with this document and the
  implementation; CI validates them against each other.
