# Modulor op API

77 ops · contract `modulor-ops/1` · generated from v1.0.0rc2 — do not edit by hand, run `python scripts/api_dump.py`.

`effects`: **doc** mutates the document · **files** writes files, document untouched · **none** pure query.

## Error codes

Every failure carries one of these stable codes (plus a message and, usually, a hint):

| code | meaning |
|---|---|
| `bad_command` | the command/batch is not shaped like {'op': ..., ...} |
| `bad_expr` | a parameter expression failed to parse or evaluate |
| `bad_format` | unsupported or malformed file format |
| `bad_json` | input text is not valid JSON |
| `bad_param` | a parameter has the wrong type, value or range |
| `bad_selector` | the selector object/string cannot be interpreted |
| `bad_target` | selection resolved to the wrong count or kind of entity |
| `bad_type` | this entity type does not support the operation |
| `degenerate` | the geometry would be invalid (zero/negative size, self-defeating input) |
| `empty_result` | the operation produced no geometry (e.g. non-overlapping booleans) |
| `empty_selection` | the selector matched no entities |
| `file_not_found` | the input file does not exist |
| `internal` | unexpected internal failure (please report) |
| `missing_param` | a required parameter was not given |
| `no_path` | the document has no file path yet (save it first) |
| `not_closed` | an open curve was used where a closed area is needed |
| `not_found` | no entity/material/level/snapshot with that name |
| `over_budget` | the request exceeds a resource budget (resolution, counts); the hint says which knob to turn |
| `recipe_error` | no recipe stored, recipe recursion, or a recipe command failed (message says which) |
| `unknown_op` | no op with that name (hint suggests close matches) |
| `unknown_param` | the op has no such parameter (hint suggests close matches) |
| `unknown_tool` | MCP: no tool with that name |

## add_arc

*effects: doc*  
Add a circular arc, CCW from start_angle to end_angle (degrees from +X).

| param | type | required | default | notes |
|---|---|---|---|---|
| `center` | point2 | yes |  | point [x, y] |
| `radius` | number | yes |  | radius (> 0) |
| `start_angle` | number | yes |  | degrees |
| `end_angle` | number | yes |  | degrees |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "add_arc", "center": [0, 0], "radius": 80, "start_angle": 0, "end_angle": 90}
```

## add_box

*effects: doc*  
Add an axis-aligned box solid.

| param | type | required | default | notes |
|---|---|---|---|---|
| `at` | point3 |  | `[0.0, 0.0, 0.0]` | anchor point |
| `size` | point3 | yes |  | [sx, sy, sz] |
| `anchor` | string |  | `"corner"` | 'at' is the min corner or the 3D center one of ['corner', 'center'] |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], volume, bbox}`

```json
{"op": "add_box", "at": [0, 0, 0], "size": [2000, 1000, 750]}
```

## add_circle

*effects: doc*  
Add a circle.

| param | type | required | default | notes |
|---|---|---|---|---|
| `center` | point2 | yes |  | point [x, y] |
| `radius` | number | yes |  | radius (> 0) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "add_circle", "center": [100, 100], "radius": 50}
```

## add_cylinder

*effects: doc*  
Add a cylinder (or cone, with radius_top) standing on its base.

| param | type | required | default | notes |
|---|---|---|---|---|
| `at` | point3 |  | `[0.0, 0.0, 0.0]` | center of the base circle |
| `radius` | number | yes |  | base radius |
| `height` | number | yes |  | height (> 0) |
| `radius_top` | number |  |  | top radius; 0 makes a cone (default: radius) |
| `segments` | integer |  | `0` | 0 = automatic |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], volume, bbox}`

```json
{"op": "add_cylinder", "at": [500, 500, 0], "radius": 150, "height": 2800}
```

## add_dim

*effects: doc*  
Add an aligned linear dimension between two points. The measured distance is rendered automatically; offset places the dimension line to the left (+) or right (-) of the p1->p2 direction.

| param | type | required | default | notes |
|---|---|---|---|---|
| `p1` | point2 | yes |  | point [x, y] |
| `p2` | point2 | yes |  | point [x, y] |
| `offset` | number |  |  | distance from measured points (default: 500mm equivalent) |
| `text` | string |  |  | override the measured value |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], value}`

```json
{"op": "add_dim", "p1": [0, 0], "p2": [4000, 0], "offset": -600}
```

## add_dim_angular

*effects: doc*  
Angular dimension: measures the CCW angle at `center` from the ray toward p1 to the ray toward p2, drawn as an arc at `radius`.

| param | type | required | default | notes |
|---|---|---|---|---|
| `center` | point2 | yes |  | point [x, y] |
| `p1` | point2 | yes |  | point on the first ray |
| `p2` | point2 | yes |  | point on the second ray |
| `radius` | number |  |  | arc placement radius (default: mean of the two point distances) |
| `text` | string |  |  | override the measured value |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], value}`

```json
{"op": "add_dim_angular", "center": [0, 0], "p1": [500, 0], "p2": [400, 400]}
```

## add_dim_radial

*effects: doc*  
Radius dimension on a circle or arc: a leader at `angle` with the text 'R<value>'.

| param | type | required | default | notes |
|---|---|---|---|---|
| `of` | select | yes |  | one circle or arc entity |
| `direction` | number |  | `45.0` | leader direction, degrees |
| `text` | string |  |  | override the measured value |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], value}`

```json
{"op": "add_dim_radial", "of": "e4", "direction": 30}
```

## add_ellipse

*effects: doc*  
Add an ellipse. Closed shape: it can be extruded, hatched and used in 2D booleans like a circle.

| param | type | required | default | notes |
|---|---|---|---|---|
| `center` | point2 | yes |  | point [x, y] |
| `rx` | number | yes |  | semi-axis along x before rotation (> 0) |
| `ry` | number | yes |  | semi-axis along y before rotation (> 0) |
| `rotation` | number |  | `0.0` | degrees CCW |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "add_ellipse", "center": [0, 0], "rx": 800, "ry": 450}
```

## add_facade

*effects: doc*  
Curtain-wall facade between two plan points: a mullion grid solid plus a glass pane solid. Panel sizes come from cols/rows or from target spacing.

| param | type | required | default | notes |
|---|---|---|---|---|
| `start` | point2 | yes |  | point [x, y] |
| `end` | point2 | yes |  | point [x, y] |
| `height` | number | yes |  | facade height (> 0) |
| `z` | number |  | `0.0` | sill elevation |
| `cols` | integer |  |  | panel columns (default: by spacing) |
| `rows` | integer |  |  | panel rows (default: by spacing) |
| `spacing` | number |  |  | target panel size (default 1500mm eq.) |
| `mullion` | number |  |  | mullion face width (default 60mm eq.) |
| `depth` | number |  |  | mullion depth (default 120mm eq.) |
| `mullion_material` | string |  |  | material name (define with add_material) |
| `glass_material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [mullions, glass], cols, rows, panel}`

```json
{"op": "add_facade", "start": [0, 0], "end": [12000, 0], "height": 8000, "spacing": 2000}
```

## add_grid

*effects: doc*  
Structural grid: labeled axis lines drawn in plan. Reference intersections anywhere a number is accepted: grid_x('B'), grid_y('3'). Axes can be explicit coordinates or {"start", "count", "spacing"} (spacing may be an expression).

| param | type | required | default | notes |
|---|---|---|---|---|
| `x` | object | yes |  | [0, 4000, 8000] or {"start": 0, "count": 5, "spacing": "bay"} |
| `y` | object | yes |  | same for the y axis |
| `x_labels` | array |  |  | default A, B, C, ... |
| `y_labels` | array |  |  | default 1, 2, 3, ... |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], x, y}`

```json
{"op": "add_grid", "x": {"start": 0, "count": 5, "spacing": "bay"}, "y": [0, 6000, 12000]}
```

## add_hatch

*effects: doc*  
Hatch the area of closed shapes with a line pattern (or a solid fill). The boundary entities are kept; the hatch is its own entity and re-clips automatically when rendered.

| param | type | required | default | notes |
|---|---|---|---|---|
| `boundary` | select | yes |  | closed shapes: circle / ellipse / closed polyline / region / room / wall footprint |
| `pattern` | string |  | `"lines"` | parallel lines, two perpendicular passes, or a solid fill one of ['lines', 'cross', 'solid'] |
| `spacing` | number |  |  | distance between hatch lines (default: boundary size / 25) |
| `angle` | number |  | `45.0` | hatch line direction, degrees |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], lines}`

```json
{"op": "add_hatch", "boundary": "e3", "pattern": "lines", "angle": 45}
```

## add_implicit

*effects: doc*  
Sculpt a solid from a math expression over x, y, z: the solid is where the expression is POSITIVE. The native way to make organic and freeform geometry. Helpers: length(...), smin/smax(a,b,k) for smooth blends, clamp, mix, abs, min, max, trig. Example sphere: '500 - length(x, y, z)'.

| param | type | required | default | notes |
|---|---|---|---|---|
| `expr` | string | yes |  | scalar field; > 0 is solid |
| `bounds` | object | yes |  | {"min": [x,y,z], "max": [x,y,z]} region to evaluate |
| `edge_length` | number |  |  | mesh resolution (default: max extent/64; smaller = finer = slower) |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], volume, bbox}`

```json
{"op": "add_implicit", "expr": "smax(400 - length(x, y, z), 300 - length(x - 350, y, z), 150)", "bounds": {"min": [-800, -800, -800], "max": [800, 800, 800]}}
```

## add_layer

*effects: doc*  
Create or update a layer. Layers are also auto-created when first referenced by a drawing op.

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string | yes |  | layer name |
| `color` | string |  |  | '#rrggbb' |
| `line_width` | number |  |  | display/print line width |
| `visible` | boolean |  |  | hidden layers are skipped by render/export |

**returns** `{layer, color, visible, line_width}`

```json
{"op": "add_layer", "name": "walls", "color": "#333333"}
```

## add_leader

*effects: doc*  
Leader annotation: an arrow at the first point, a line through the given points, and text at the last point.

| param | type | required | default | notes |
|---|---|---|---|---|
| `points` | points | yes |  | arrow tip first, text end last (2+ points) |
| `text` | string | yes |  | the annotation text |
| `height` | number |  |  | text height (default: 250mm equivalent) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "add_leader", "points": [[1200, 800], [1800, 1400]], "text": "waterproofing"}
```

## add_level

*effects: doc*  
Define a named building level (storey). Reference it anywhere a number is accepted: "level('L2')" is its elevation, "level_top('L2')" is elevation + height.

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string | yes |  | e.g. 'L1', 'roof' |
| `elevation` | number | yes |  | level elevation (z) |
| `height` | number |  |  | storey height (enables level_top) |

**returns** `{levels}`

```json
{"op": "add_level", "name": "L2", "elevation": 3200, "height": 3200}
```

## add_line

*effects: doc*  
Add a straight line segment.

| param | type | required | default | notes |
|---|---|---|---|---|
| `start` | point2 | yes |  | point [x, y] |
| `end` | point2 | yes |  | point [x, y] |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "add_line", "start": [0, 0], "end": [1000, 0]}
```

## add_material

*effects: doc*  
Create or update a material (used by 3D solids; exported to glTF/OBJ).

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string | yes |  | material name |
| `color` | string | yes |  | '#rrggbb' |
| `metallic` | number |  | `0.0` | PBR metallic, 0-1 |
| `roughness` | number |  | `0.8` | PBR roughness, 0-1 |

**returns** `{material, color, metallic, roughness}`

```json
{"op": "add_material", "name": "concrete", "color": "#b8b4ab"}
```

## add_opening

*effects: doc*  
Cut a door or window into a wall. Position is the distance along the wall centerline to the opening center.

| param | type | required | default | notes |
|---|---|---|---|---|
| `wall` | select | yes |  | the wall: id, tag or selector (must match exactly one wall) |
| `along` | number | yes |  | distance along the centerline to the opening center |
| `width` | number | yes |  | opening width (> 0) |
| `type` | string |  | `"door"` | drawing symbol + default sill/head one of ['door', 'window'] |
| `sill` | number |  |  | bottom height (default: door 0, window 900mm eq.) |
| `head` | number |  |  | top height (default: door 2100, window 2400mm eq.) |

**returns** `{modified: [wall id], openings}`

```json
{"op": "add_opening", "wall": "e1", "along": 1200, "width": 900, "type": "door"}
```

## add_polyline

*effects: doc*  
Add a polyline (open or closed). Closed polylines bound an area and can be extruded or used in 2D booleans.

| param | type | required | default | notes |
|---|---|---|---|---|
| `points` | points | yes |  | list of [x, y] points |
| `closed` | boolean |  | `false` | close the loop (bounds an area) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "add_polyline", "points": [[0, 0], [500, 0], [500, 300], [0, 300]], "closed": true}
```

## add_rect

*effects: doc*  
Add an axis-aligned rectangle (a closed polyline), optionally rotated.

| param | type | required | default | notes |
|---|---|---|---|---|
| `at` | point2 | yes |  | anchor point [x, y] |
| `width` | number | yes |  | size along x (> 0) |
| `height` | number | yes |  | size along y (> 0) |
| `anchor` | string |  | `"corner"` | 'at' is the lower-left corner or the center one of ['corner', 'center'] |
| `rotation` | number |  | `0.0` | degrees CCW about the anchor |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "add_rect", "at": [0, 0], "width": 400, "height": 250}
```

## add_roof

*effects: doc*  
Generate a roof solid over a closed footprint: 'flat' slab, 'shed' single slope, or 'gable' double slope with a central ridge. direction sets the ridge/slope orientation in degrees.

| param | type | required | default | notes |
|---|---|---|---|---|
| `footprint` | select | yes |  | closed 2D shape |
| `kind` | string |  | `"gable"` | roof shape one of ['flat', 'shed', 'gable'] |
| `pitch` | number |  | `30.0` | slope, degrees (5-75) |
| `thickness` | number |  |  | slab thickness (default 200mm eq.) |
| `overhang` | number |  | `0.0` | eave extension beyond the footprint |
| `z` | number |  | `0.0` | eave elevation (expressions: "level_top('L2')") |
| `direction` | number |  | `0.0` | ridge axis (gable) or downhill axis (shed), degrees |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], ridge_height, volume, bbox}`

```json
{"op": "add_roof", "footprint": {"tags": ["plan"]}, "kind": "gable", "pitch": 35, "overhang": 600, "z": "level_top('L2')"}
```

## add_room

*effects: doc*  
Declare a room/zone/site: a named program area. It renders as a boundary + name + live area label in plan, and feeds the 'program' report. Boundary can be points or an existing closed shape.

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string | yes |  | room/zone name |
| `points` | points |  |  | boundary polygon (or use 'boundary') |
| `boundary` | select |  |  | existing closed shape to take the boundary from |
| `level` | string |  |  | level name (for the program report) |
| `kind` | string |  | `"room"` | rooms count toward the program area one of ['room', 'zone', 'site'] |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], area}`

```json
{"op": "add_room", "name": "LIVING", "level": "L1", "points": [[0, 0], [5000, 0], [5000, 4000], [0, 4000]]}
```

## add_sphere

*effects: doc*  
Add a sphere.

| param | type | required | default | notes |
|---|---|---|---|---|
| `center` | point3 | yes |  | point [x, y, z] |
| `radius` | number | yes |  | radius (> 0) |
| `segments` | integer |  | `0` | 0 = automatic |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], volume, bbox}`

```json
{"op": "add_sphere", "center": [0, 0, 500], "radius": 300}
```

## add_spline

*effects: doc*  
Add a smooth curve through the given points (centripetal Catmull-Rom). Closed splines bound an area: they can be extruded, lofted, swept and used in 2D booleans like any closed shape.

| param | type | required | default | notes |
|---|---|---|---|---|
| `points` | points | yes |  | points the curve passes through |
| `closed` | boolean |  | `false` | close the loop (bounds an area) |
| `samples` | integer |  | `12` | curve segments between points (quality vs size) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], length}`

```json
{"op": "add_spline", "closed": true, "points": [[0, 0], [4000, 1500], [7000, 0], [5000, -2500]]}
```

## add_stair

*effects: doc*  
Straight stair flight as a solid. Riser/tread are computed from the rise using the comfort rule (2R + T = 630mm eq.) and reported back; the flight runs along +X from 'at' before rotation.

| param | type | required | default | notes |
|---|---|---|---|---|
| `at` | point2 | yes |  | start of the first riser |
| `rise` | number | yes |  | total height (e.g. "level('L2')-level('L1')") |
| `width` | number |  |  | flight width (default 1100mm eq.) |
| `direction` | number |  | `0.0` | run direction, degrees |
| `z` | number |  | `0.0` | base elevation |
| `riser_max` | number |  |  | max riser height (default 180mm eq.) |
| `tread` | number |  |  | tread depth (default from comfort rule) |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], risers, riser, tread, run}`

```json
{"op": "add_stair", "at": [1000, 500], "rise": 3200, "direction": 90}
```

## add_surface

*effects: doc*  
Doubly-curved surface slab: z = f(x, y) over a rectangle, given thickness. The freeform roof/canopy tool — write the surface as math, e.g. a vault: '6000 - 0.0004*(x-10000)**2 + 0.1*y'. Helpers: sin/cos/length/smin/smax/clamp/mix.

| param | type | required | default | notes |
|---|---|---|---|---|
| `expr` | string | yes |  | height field z = f(x, y) |
| `bounds` | object | yes |  | {"min": [x, y], "max": [x, y]} |
| `thickness` | number | yes |  | slab thickness (> 0) |
| `samples` | integer |  | `48` | resolution across the larger side (16-128) |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], z_range, volume, bbox}`

```json
{"op": "add_surface", "expr": "3000 + 1500*sin(x/3000)*cos(y/4000)", "bounds": {"min": [0, 0], "max": [20000, 15000]}, "thickness": 250}
```

## add_text

*effects: doc*  
Add a text label.

| param | type | required | default | notes |
|---|---|---|---|---|
| `at` | point2 | yes |  | baseline-left anchor |
| `text` | string | yes |  | the label text |
| `height` | number |  |  | cap height in doc units (default: 250mm equivalent) |
| `rotation` | number |  | `0.0` | degrees CCW |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "add_text", "at": [200, 150], "text": "KITCHEN", "height": 200}
```

## add_torus

*effects: doc*  
Add a torus lying in the XY plane (donut axis = +Z through `at`).

| param | type | required | default | notes |
|---|---|---|---|---|
| `at` | point3 |  | `[0.0, 0.0, 0.0]` | center of the torus |
| `radius` | number | yes |  | ring radius: center to tube center |
| `tube_radius` | number | yes |  | tube radius (> 0, < radius) |
| `segments` | integer |  | `0` | 0 = automatic |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], volume, bbox}`

```json
{"op": "add_torus", "at": [0, 0, 500], "radius": 400, "tube_radius": 80}
```

## add_wall

*effects: doc*  
Add a wall along a centerline path. Walls render as double lines in plan and extrude to 3D automatically. Openings (doors/windows) are cut with add_opening.

| param | type | required | default | notes |
|---|---|---|---|---|
| `path` | points | yes |  | centerline [[x,y], ...] |
| `thickness` | number | yes |  | wall thickness (> 0) |
| `height` | number |  |  | 3D height (default: 3000mm equivalent) |
| `smooth` | boolean |  | `false` | run a Catmull-Rom spline through the path points: curved walls |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |
| `material` | string |  |  | material for 3D rendering/export |

**returns** `{created: [id], length}`

```json
{"op": "add_wall", "path": [[0, 0], [6000, 0], [6000, 4000]], "thickness": 200, "tag": "exterior"}
```

## array

*effects: doc*  
Repeat entities in a grid or around a center (polar). The original counts as the first item.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `kind` | string | yes |  | rectangular lattice or around a center one of ['grid', 'polar'] |
| `nx` | integer |  | `1` | grid: columns |
| `ny` | integer |  | `1` | grid: rows |
| `dx` | number |  | `0.0` | grid: column spacing |
| `dy` | number |  | `0.0` | grid: row spacing |
| `count` | integer |  |  | polar: total item count |
| `center` | point2 |  | `[0.0, 0.0]` | polar: rotation center |
| `angle` | number |  | `360.0` | polar: total angle (degrees) |

**returns** `{created: [ids]}`

```json
{"op": "array", "select": "e9", "kind": "grid", "nx": 4, "ny": 2, "dx": 3000, "dy": 4000}
```

## boolean_2d

*effects: doc*  
2D boolean between closed shapes. Inputs are consumed unless keep=true; the result is one region entity.

| param | type | required | default | notes |
|---|---|---|---|---|
| `kind` | string | yes |  | boolean operation one of ['union', 'difference', 'intersect', 'xor'] |
| `a` | select | yes |  | first operand(s), unioned together |
| `b` | select |  |  | second operand(s); not needed for plain union |
| `keep` | boolean |  | `false` | keep input entities |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], area}`

```json
{"op": "boolean_2d", "kind": "difference", "a": "e1", "b": ["e2", "e3"]}
```

## boolean_3d

*effects: doc*  
3D boolean between solids (walls are converted automatically). Inputs are consumed unless keep=true; result is one solid.

| param | type | required | default | notes |
|---|---|---|---|---|
| `kind` | string | yes |  | boolean operation one of ['union', 'difference', 'intersect'] |
| `a` | select | yes |  | first operand(s), unioned together |
| `b` | select |  |  | second operand(s); not needed for plain union |
| `keep` | boolean |  | `false` | keep input entities |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], volume, bbox}`

```json
{"op": "boolean_3d", "kind": "difference", "a": "e10", "b": "e11"}
```

## chamfer

*effects: doc*  
Cut the corners of polylines with straight bevels at the given setback distance (in place).

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | polyline entities (open or closed) |
| `distance` | number | yes |  | setback from each corner |

**returns** `{modified: [ids], corners, clamped}`

```json
{"op": "chamfer", "select": "e2", "distance": 30}
```

## copy

*effects: doc*  
Copy entities, translating each copy by `by` (repeated `count` times).

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `by` | point3 | yes |  | [dx, dy] or [dx, dy, dz] per copy |
| `count` | integer |  | `1` | number of copies |

**returns** `{created: [ids]}`

```json
{"op": "copy", "select": "e5", "by": [3000, 0], "count": 3}
```

## define_block

*effects: doc*  
Define a reusable block from existing entities. By default the source entities are replaced by one instance in place (geometry is unchanged); pass replace=false to keep them and only store the definition.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | entities to capture (grids cannot be blocked) |
| `name` | string | yes |  | block name (must be new) |
| `base` | point2 |  | `[0.0, 0.0]` | local origin: insert_block 'at' lands here |
| `replace` | boolean |  | `true` | swap the source entities for an instance |

**returns** `{created: [instance id] or [], block, count}`

```json
{"op": "define_block", "select": {"tags": ["window"]}, "name": "win-900", "base": [0, 0]}
```

## define_param

*effects: doc*  
Declare a design parameter with a default value — sets it only if it does not exist yet. Use this inside recipes so `regenerate` overrides are not clobbered.

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string | yes |  | parameter name (identifier) |
| `value` | number | yes |  | default value |

**returns** `{name, value, defined}`

```json
{"op": "define_param", "name": "bay", "value": 4000}
```

## deform

*effects: doc*  
Non-rigid deformation of solids (in place): twist about the vertical axis, taper along the height, or bend along x into an arc. Use refine to subdivide first so curved results look smooth.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | solid entities |
| `kind` | string | yes |  | deformation type one of ['twist', 'taper', 'bend'] |
| `amount` | number | yes |  | twist/bend: total degrees; taper: scale factor at the top (e.g. 0.4) |
| `plane` | string |  | `"xz"` | bend only: bend vertically (xz) or in plan (xy) one of ['xz', 'xy'] |
| `refine` | integer |  | `3` | mesh subdivision before warping (0 = none) |

**returns** `{modified: [ids]}`

```json
{"op": "deform", "select": {"tags": ["tower"]}, "kind": "twist", "amount": 120}
```

## delete

*effects: doc*  
Delete entities.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |

**returns** `{deleted: n}`

```json
{"op": "delete", "select": {"layers": ["draft"]}}
```

## diff

*effects: none*  
Compare the current model against a saved snapshot: parameter changes, entity additions/removals/modifications, and metric deltas. The review tool for design options.

| param | type | required | default | notes |
|---|---|---|---|---|
| `against` | string | yes |  | snapshot name (see 'snapshots') |

**returns** `{params_changed, added, removed, modified, metrics}`

```json
{"op": "diff", "against": "option-a"}
```

## doc_info

*effects: none*  
Summary of the document: units, layers, entity counts, bounding box.

**returns** `{units, name, layers, counts, bbox}`

```json
{"op": "doc_info"}
```

## doc_new

*effects: doc*  
Reset the document to an empty state.

| param | type | required | default | notes |
|---|---|---|---|---|
| `units` | string |  | `"mm"` | document units one of ['mm', 'cm', 'm', 'in', 'ft'] |
| `name` | string |  | `"untitled"` | document name |

**returns** `{units, name}`

```json
{"op": "doc_new", "units": "mm", "name": "bracket"}
```

## export

*effects: files*  
Export to a file; format from the extension. 2D formats: .svg .dxf (drawings, dims, walls in plan). 3D formats: .obj .stl .glb (solids + walls as meshes). .ifc exports a semantic IFC4 BIM model (walls with openings, storeys from levels, grids, rooms as spaces with areas, other solids as proxies) for Revit/Archicad/checkers. .png renders an image, .json saves a document copy.

| param | type | required | default | notes |
|---|---|---|---|---|
| `path` | string | yes |  | output file, one of ('.svg', '.dxf', '.png', '.obj', '.stl', '.glb', '.ifc', '.json') |
| `select` | select |  | `"all"` | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `width` | integer |  | `1200` | png only |
| `height` | integer |  | `900` | png only |
| `camera` | object |  |  | png only: named view ("iso", "top", "front", ...) or {"eye": [x,y,z], "target": [x,y,z], "fov": 45} |

**returns** `format-specific summary, always includes {path}`

```json
{"op": "export", "path": "out/plan.dxf"}
```

## extrude

*effects: doc*  
Extrude closed 2D shapes vertically into solids (one solid per selected entity). The profile entities are kept unless keep=false.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | closed shapes: circle / closed polyline / region / wall footprint |
| `height` | number | yes |  | extrusion height (+Z) |
| `z` | number |  | `0.0` | base elevation |
| `twist` | number |  | `0.0` | degrees of twist over the height |
| `scale_top` | number |  | `1.0` | scale of the top vs the bottom |
| `divisions` | integer |  | `0` | vertical subdivisions for twist |
| `keep` | boolean |  | `true` | keep the profile entities |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [ids], volume}`

```json
{"op": "extrude", "select": "e2", "height": 3000}
```

## fillet

*effects: doc*  
Round the corners of polylines with arcs of the given radius (in place). Radius is clamped per corner when segments are short.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | polyline entities (open or closed) |
| `radius` | number | yes |  | corner arc radius (> 0) |

**returns** `{modified: [ids], corners, clamped}`

```json
{"op": "fillet", "select": "e2", "radius": 50}
```

## find

*effects: none*  
Spatial query: which entities are at/near a point, or inside a box? Results are sorted by distance. The fastest way to rebuild your mental map of a drawing.

| param | type | required | default | notes |
|---|---|---|---|---|
| `at` | point3 |  |  | query point [x, y] or [x, y, z] |
| `radius` | number |  |  | with 'at': only entities within this distance |
| `bbox` | object |  |  | {"min": [x,y(,z)], "max": [x,y(,z)]}: only entities whose bounds overlap this box |
| `select` | select |  | `"all"` | restrict the search to these entities |
| `limit` | integer |  | `10` | max results returned |

**returns** `{found: [{id, type, layer, tag?, distance, bbox}]}`

```json
{"op": "find", "at": [2500, 1200], "radius": 500}
```

## get

*effects: none*  
Full data of one entity, including geometry.

| param | type | required | default | notes |
|---|---|---|---|---|
| `id` | string | yes |  | entity id, e.g. 'e3' |

**returns** `{id, entity, bbox}`

```json
{"op": "get", "id": "e3"}
```

## help

*effects: none*  
Introspect the API: list all ops, or full parameter docs for one op.

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string |  |  | op name; omit to list all ops |

**returns** `{ops: [{op, doc, effects}]} or one op's full description`

```json
{"op": "help", "name": "add_wall"}
```

## import_dxf

*effects: doc*  
Import entities from a DXF file (ASCII, R12 through current). Supported: LINE, CIRCLE, ARC, LWPOLYLINE/POLYLINE (with arc bulges), TEXT, MTEXT, SPLINE, ELLIPSE, LEADER, HATCH, DIMENSION, INSERT — plus layers with colors. Named blocks become document blocks with instance entities (semantic preservation); set blocks='explode' for flat copies. Unsupported entity types are counted in 'skipped', never silently dropped. This is how you take over an existing human drawing.

| param | type | required | default | notes |
|---|---|---|---|---|
| `path` | string | yes |  | input .dxf file |
| `scale` | number |  | `1.0` | multiply all coordinates (unit conversion) |
| `layer_prefix` | string |  | `""` | prefix imported layer names, e.g. 'dxf/' |
| `blocks` | string |  | `"native"` | map INSERT to block instances, or expand to flat entity copies one of ['native', 'explode'] |

**returns** `{created: [ids], imported: {TYPE: n}, skipped: {TYPE: n}, layers, blocks?, dxf_units?, warnings?}`

```json
{"op": "import_dxf", "path": "site_plan.dxf"}
```

## insert_block

*effects: doc*  
Place an instance of a block: the block's base point lands on `at`, rotated and uniformly scaled. Use array/copy for repetition.

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string | yes |  | a defined block (see define_block) |
| `at` | point2 | yes |  | insertion point |
| `rotation` | number |  | `0.0` | degrees CCW |
| `scale` | number |  | `1.0` | uniform factor (> 0) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "insert_block", "name": "win-900", "at": [3200, 0], "rotation": 90}
```

## list

*effects: none*  
List entities (id, type, layer, tag and a one-line geometric summary).

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select |  | `"all"` | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `bbox` | boolean |  | `false` | include per-entity bounding boxes |

**returns** `{entities: [{id, type, layer, tag?, brief, bbox?}]}`

```json
{"op": "list", "select": {"layers": ["walls"]}}
```

## list_layers

*effects: none*  
List layers and their properties.

**returns** `{layers: {name: {color, visible, line_width}}}`

```json
{"op": "list_layers"}
```

## loft

*effects: doc*  
Skin a solid through a stack of closed profiles at increasing heights (straight/ruled between sections — add more sections for curvature, or run 'smooth' after). Profiles may differ in shape: each is resampled to the same point count.

| param | type | required | default | notes |
|---|---|---|---|---|
| `sections` | array | yes |  | [{"select": <selector>, "z": height}, ...] bottom to top, single-contour closed shapes |
| `samples` | integer |  | `64` | points per section ring |
| `divisions` | integer |  | `0` | smooth interpolation: extra rings between sections, traced with a vertical spline (8-16 makes flowing surfaces; 0 = ruled) |
| `keep` | boolean |  | `true` | keep the section entities |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], volume, bbox}`

```json
{"op": "loft", "sections": [{"select": "e1", "z": 0}, {"select": "e2", "z": 15000}, {"select": "e3", "z": 30000}]}
```

## measure

*effects: none*  
Measure geometry: distance between two points, or length / area / volume / bbox of selected entities.

| param | type | required | default | notes |
|---|---|---|---|---|
| `kind` | string | yes |  | what to measure one of ['distance', 'length', 'area', 'volume', 'bbox'] |
| `p1` | point3 |  |  | distance: first point |
| `p2` | point3 |  |  | distance: second point |
| `select` | select |  |  | length/area/volume/bbox: target entities |

**returns** `{value} or {bbox, size, center}`

```json
{"op": "measure", "kind": "area", "select": "e4"}
```

## mirror

*effects: doc*  
Mirror entities across the line p1->p2 (solids: across the vertical plane through that line). Set copy=true to keep the original.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `p1` | point2 | yes |  | point [x, y] |
| `p2` | point2 | yes |  | point [x, y] |
| `copy` | boolean |  | `false` | keep the original |

**returns** `{modified: [ids]} or {created: [ids]}`

```json
{"op": "mirror", "select": "e4", "p1": [0, 0], "p2": [0, 100], "copy": true}
```

## move

*effects: doc*  
Translate entities by a vector. 2D entities ignore dz.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `by` | point3 | yes |  | [dx, dy] or [dx, dy, dz] |

**returns** `{modified: [ids]}`

```json
{"op": "move", "select": ["e1", "e2"], "by": [0, 2500]}
```

## offset

*effects: doc*  
Offset closed shapes outward (+) or inward (-) by a distance. Produces a region; the source is kept.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | closed shapes (circle/closed polyline/region/wall footprint) |
| `delta` | number | yes |  | + grows, - shrinks |
| `join` | string |  | `"miter"` | corner treatment of the offset contour one of ['round', 'miter', 'square'] |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id]}`

```json
{"op": "offset", "select": "e2", "delta": 150}
```

## params

*effects: none*  
List design parameters, levels and the stored recipe size.

**returns** `{params, levels, recipe_commands}`

```json
{"op": "params"}
```

## program

*effects: none*  
The area program: every room/zone/site with its level and area, plus totals by kind and by name. The brief-checking report.

**returns** `{rooms: [...], total_area, by_name, by_level}`

```json
{"op": "program"}
```

## project

*effects: doc*  
Project solids/walls to a 2D outline region. axis 'z' gives the plan footprint (x,y); 'x' the side elevation outline (y,z); 'y' the front elevation outline (x,z). Sources are kept.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select |  | `{"types": ["solid", "wall"]}` | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `axis` | string |  | `"z"` | viewing direction one of ['z', 'x', 'y'] |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [ids]}`

```json
{"op": "project", "select": "e12", "axis": "y", "layer": "elevation"}
```

## recipe_set

*effects: doc*  
Store the command list that generates this model (the design intent). After this, `regenerate` rebuilds the whole model from the recipe — typically after `set_param`. Use `define_param` inside the recipe for defaults.

| param | type | required | default | notes |
|---|---|---|---|---|
| `commands` | array | yes |  | ordered op commands; expressions in numeric fields are kept live |
| `run` | boolean |  | `false` | also regenerate from it immediately |

**returns** `{recipe_commands}`

```json
{"op": "recipe_set", "commands": [{"op": "define_param", "name": "bay", "value": 4000}, {"op": "add_grid", "x": {"start": 0, "count": 5, "spacing": "bay"}, "y": {"start": 0, "count": 3, "spacing": "bay*1.5"}}], "run": true}
```

## regenerate

*effects: doc*  
Rebuild the model from the stored recipe: geometry is cleared, parameters survive (optionally overridden), every expression is re-evaluated. This is how a design stays coordinated when a parameter changes.

| param | type | required | default | notes |
|---|---|---|---|---|
| `params` | object |  |  | {"name": value, ...} parameter overrides applied before rebuilding |

**returns** `{regenerated, entities, params}`

```json
{"op": "regenerate", "params": {"bay": 5000}}
```

## render

*effects: files*  
Render a PNG image of the model so it can be inspected visually. mode 'plan' draws the 2D drawing; 'shaded' draws solids/walls in 3D; 'auto' picks shaded when solids exist.

| param | type | required | default | notes |
|---|---|---|---|---|
| `path` | string | yes |  | output .png file |
| `mode` | string |  | `"auto"` | 2D drawing or 3D view; auto picks by content one of ['auto', 'plan', 'shaded'] |
| `select` | select |  | `"all"` | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `width` | integer |  | `1200` | image width, px |
| `height` | integer |  | `900` | image height, px |
| `camera` | object |  |  | shaded only: named view ("iso", "iso_left", "top", "front", "right", ...) or {"eye": [x,y,z], "target": [x,y,z], "fov": 45} |
| `labels` | boolean |  | `false` | overlay entity ids/tags on the image so you can map what you see back to entities |

**returns** `{path, width, height, ...}`

```json
{"op": "render", "path": "out/iso.png", "mode": "shaded", "camera": "iso"}
```

## restore

*effects: doc*  
Replace the document with a previously saved snapshot.

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string | yes |  | snapshot name |

**returns** `{restored, entities}`

```json
{"op": "restore", "name": "before-booleans"}
```

## revolve

*effects: doc*  
Revolve closed 2D profiles around the vertical axis through `axis_point` to make solids of revolution. In the profile, x = distance from the axis (must be >= 0 after shifting), y = height (becomes z).

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | closed profile(s) |
| `angle` | number |  | `360.0` | sweep angle, degrees |
| `axis_point` | point2 |  | `[0.0, 0.0]` | 2D point the vertical axis passes through (profile is measured from its x) |
| `segments` | integer |  | `0` | 0 = automatic |
| `keep` | boolean |  | `true` | keep the profile entities |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [ids]}`

```json
{"op": "revolve", "select": "e3", "angle": 360}
```

## rotate

*effects: doc*  
Rotate entities CCW (degrees). 2D rotation is about `center` in the plane; solids rotate about a vertical axis through `center` unless `axis` is given.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `angle` | number | yes |  | degrees CCW |
| `center` | point3 |  | `[0.0, 0.0, 0.0]` | point [x, y, z] |
| `axis` | point3 |  |  | rotation axis for solids (default [0,0,1]) |

**returns** `{modified: [ids]}`

```json
{"op": "rotate", "select": "e7", "angle": 90, "center": [500, 500]}
```

## scale

*effects: doc*  
Scale entities about a center point. Pass one factor for uniform scaling or [fx, fy] / [fx, fy, fz].

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `factor` | object | yes |  | number or [fx, fy] or [fx, fy, fz] |
| `center` | point3 |  | `[0.0, 0.0, 0.0]` | point [x, y, z] |

**returns** `{modified: [ids]}`

```json
{"op": "scale", "select": "e2", "factor": 2.0, "center": [0, 0]}
```

## set_param

*effects: doc*  
Set a design parameter. Any numeric field in any op can reference it by name in an expression: {"width": "bay*2"}. Combine with `regenerate` to rebuild the model with the new value.

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string | yes |  | parameter name (identifier) |
| `value` | number | yes |  | new value |

**returns** `{name, value}`

```json
{"op": "set_param", "name": "bay", "value": 5000}
```

## set_units

*effects: doc*  
Change document units (does NOT rescale existing geometry).

| param | type | required | default | notes |
|---|---|---|---|---|
| `units` | string | yes |  | new document units one of ['mm', 'cm', 'm', 'in', 'ft'] |

**returns** `{units}`

```json
{"op": "set_units", "units": "m"}
```

## shell

*effects: doc*  
Hollow solids into shells of the given wall thickness (in place), by eroding a copy and subtracting it. Closed shells — combine with boolean_3d or slice to open them.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | solid entities |
| `thickness` | number | yes |  | wall thickness (> 0) |
| `segments` | integer |  | `12` | erosion sphere quality |

**returns** `{modified: [ids]}`

```json
{"op": "shell", "select": {"tags": ["body"]}, "thickness": 2}
```

## slice

*effects: doc*  
Horizontal section: cut solids/walls at height z and produce 2D region(s) of the cut. Sources are kept.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select |  | `{"types": ["solid", "wall"]}` | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `z` | number | yes |  | section height |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [ids]}`

```json
{"op": "slice", "select": "all", "z": 1200, "layer": "section"}
```

## smooth

*effects: doc*  
Smooth solids in place: facet edges flatter than `angle` degrees are rounded into curvature-continuous patches (sharper edges are kept crisp), then the mesh is refined. Great after loft/deform.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | solid entities |
| `angle` | number |  | `52.5` | edges with a dihedral angle below this get smoothed; above it they stay sharp |
| `refine` | integer |  | `3` | subdivision level (2-6 typical) |

**returns** `{modified: [ids], triangles}`

```json
{"op": "smooth", "select": {"tags": ["shell"]}, "angle": 60}
```

## snapshot

*effects: files*  
Save a named snapshot of the whole document (cheap insurance before risky boolean/transform sequences).

| param | type | required | default | notes |
|---|---|---|---|---|
| `name` | string |  |  | snapshot name (default: timestamp) |

**returns** `{snapshot, entities}`

```json
{"op": "snapshot", "name": "before-booleans"}
```

## snapshots

*effects: none*  
List saved snapshots of this document.

**returns** `{snapshots: [{name, modified, size}]}`

```json
{"op": "snapshots"}
```

## solidify

*effects: doc*  
Convert walls into plain solid entities (so you can boolean them with other solids). The wall entity is replaced.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | wall entities |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [ids]}`

```json
{"op": "solidify", "select": {"types": ["wall"]}}
```

## sweep

*effects: doc*  
Sweep a closed profile along a 3D path to make a solid (tubes, ribbons, curved beams). The profile is centered on its own centroid and carried along the path with minimal twisting (parallel transport); profile x/y map to the path's normal/binormal.

| param | type | required | default | notes |
|---|---|---|---|---|
| `profile` | select | yes |  | one closed single-contour shape |
| `path` | array | yes |  | [[x,y,z], ...] (open; >= 2 points) |
| `smooth` | boolean |  | `true` | spline the path through its points |
| `twist` | number |  | `0.0` | degrees of twist over the path |
| `scale_end` | number |  | `1.0` | profile scale at the far end |
| `samples` | integer |  | `48` | points around the profile |
| `keep` | boolean |  | `true` | keep the profile entity |
| `material` | string |  |  | material name (define with add_material) |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |

**returns** `{created: [id], volume, bbox}`

```json
{"op": "sweep", "profile": "e1", "twist": 90, "path": [[0, 0, 0], [0, 2000, 6000], [0, 8000, 9000]]}
```

## update

*effects: doc*  
Change non-geometric properties of entities: layer, tag, material.

| param | type | required | default | notes |
|---|---|---|---|---|
| `select` | select | yes |  | selector: "all", an id like "e3", a list of ids, or {"layers": [...], "types": [...], "tags": [...]} |
| `layer` | string |  |  | target layer (created on first use) |
| `tag` | string |  |  | optional label for later selection |
| `material` | string |  |  | material name (solids/walls) |

**returns** `{modified: [ids]}`

```json
{"op": "update", "select": "e3", "layer": "furniture"}
```

## validate

*effects: none*  
Check the document for problems: degenerate entities, broken meshes, openings outside their walls, references to missing materials.

**returns** `{valid, problems: [{id, code, message}]}`

```json
{"op": "validate"}
```
