# Modulor prompt cookbook

Battle-tested command patterns for agents. Every recipe is a complete,
runnable batch (`modulor run model.json -` with the JSON on stdin).

## 1. Floor plan with openings and dimensions

```json
[{"op":"add_wall","path":[[0,0],[8000,0],[8000,5000],[0,5000],[0,0]],
  "thickness":240,"height":2900,"tag":"ext"},
 {"op":"add_wall","path":[[5000,0],[5000,5000]],"thickness":120,"tag":"part"},
 {"op":"add_opening","wall":{"tags":["ext"]},"along":1500,"width":1000,"type":"door"},
 {"op":"add_opening","wall":{"tags":["ext"]},"along":6200,"width":1800,"type":"window"},
 {"op":"add_dim","p1":[0,0],"p2":[8000,0],"offset":-800},
 {"op":"add_room","name":"LIVING","points":[[0,0],[5000,0],[5000,5000],[0,5000]]},
 {"op":"render","path":"plan.png","mode":"plan"},
 {"op":"export","path":"plan.dxf"}]
```

## 2. Parametric building (change one number, rebuild everything)

```json
[{"op":"recipe_set","run":true,"commands":[
  {"op":"define_param","name":"bay","value":4000},
  {"op":"add_grid","x":{"start":0,"count":5,"spacing":"bay"},
   "y":{"start":0,"count":3,"spacing":"bay*1.2"}},
  {"op":"add_cylinder","at":[0,0,0],"radius":180,"height":10500,"tag":"col"},
  {"op":"array","select":{"tags":["col"]},"kind":"grid",
   "nx":5,"ny":3,"dx":"bay","dy":"bay*1.2"}]}]
```

then: `[{"op":"regenerate","params":{"bay":5000}}]` — every column moves.

## 3. Mechanical part to 3D print

```json
[{"op":"add_rect","at":[0,0],"width":120,"height":80,"tag":"plate"},
 {"op":"fillet","select":{"tags":["plate"]},"radius":8},
 {"op":"add_circle","center":[15,15],"radius":5,"tag":"hole"},
 {"op":"array","select":{"tags":["hole"]},"kind":"grid","nx":2,"ny":2,"dx":90,"dy":50},
 {"op":"boolean_2d","kind":"difference","a":{"tags":["plate"]},
  "b":{"types":["circle"]},"tag":"profile"},
 {"op":"extrude","select":{"tags":["profile"]},"height":12,"keep":false,"tag":"body"},
 {"op":"measure","kind":"volume","select":{"tags":["body"]}},
 {"op":"export","path":"part.stl"}]
```

## 4. Take over an existing DXF drawing

```json
[{"op":"import_dxf","path":"site_plan.dxf"},
 {"op":"render","path":"imported.png","mode":"plan","labels":true}]
```

Look at `imported.png`, then query what you see:
`[{"op":"find","at":[12500,8000],"radius":500}]` →
`[{"op":"get","id":"e42"}]` → modify → re-export.

## 5. Freeform (Zaha vocabulary)

```json
[{"op":"add_spline","closed":true,"tag":"s0","points":[[16,0],[0,11],[-16,0],[0,-11]]},
 {"op":"add_spline","closed":true,"tag":"s1","points":[[11,6],[-1,13],[-13,2],[1,-7]]},
 {"op":"add_circle","center":[5,2],"radius":6,"tag":"s2"},
 {"op":"loft","sections":[{"select":{"tags":["s0"]},"z":0},
                          {"select":{"tags":["s1"]},"z":42},
                          {"select":{"tags":["s2"]},"z":82}],
  "samples":96,"divisions":12,"keep":false,"tag":"tower"},
 {"op":"deform","select":{"tags":["tower"]},"kind":"twist","amount":40}]
```

Organic blobs: `{"op":"add_implicit","expr":"smax(7-length(x,y,z-4), 5-length(x-6,y,z-3), 3)","bounds":{"min":[-10,-8,0],"max":[14,8,12]}}`.
Doubly-curved canopy: `{"op":"add_surface","expr":"3000+1500*sin(x/3000)*cos(y/4000)","bounds":{"min":[0,0],"max":[20000,15000]},"thickness":250}`.

## 6. BIM handoff to Revit

```json
[{"op":"add_level","name":"L1","elevation":0,"height":3500},
 {"op":"add_level","name":"L2","elevation":3500,"height":3500},
 {"op":"add_grid","x":[0,4000,8000],"y":[0,5000]},
 {"op":"add_wall","path":[[0,0],[8000,0],[8000,5000],[0,5000],[0,0]],
  "thickness":240,"height":3500,"tag":"ext"},
 {"op":"add_opening","wall":{"tags":["ext"]},"along":1500,"width":1000,"type":"door"},
 {"op":"add_room","name":"OFFICE","level":"L1",
  "points":[[0,0],[5000,0],[5000,5000],[0,5000]]},
 {"op":"export","path":"building.ifc"}]
```

Walls arrive as IfcWall with real openings; levels as storeys; rooms as
schedulable IfcSpace.

## 7. Safe experimentation

```json
[{"op":"add_box","at":[0,0,0],"size":[60,40,30],"tag":"body"},
 {"op":"add_cylinder","at":[30,20,-5],"radius":10,"height":40,"tag":"cut"},
 {"op":"snapshot","name":"before"},
 {"op":"boolean_3d","kind":"difference","a":{"tags":["body"]},"b":{"tags":["cut"]}}]
```

Bad result? `[{"op":"restore","name":"before"}]`.
Comparing options? `[{"op":"diff","against":"before"}]`.

## 8. Self-check ritual (end every modeling session with this)

```json
[{"op":"validate"},
 {"op":"measure","kind":"bbox","select":"all"},
 {"op":"render","path":"final_iso.png","mode":"shaded","camera":"iso"},
 {"op":"render","path":"final_plan.png","mode":"plan"}]
```

Read both images before declaring success.
