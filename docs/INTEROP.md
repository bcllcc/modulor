# Interoperability contract

**Principle: what Modulor produces must open in mainstream CAD as
editable native objects — and what those tools produce must come back
without silent loss.** This page is the normative statement of what is
guaranteed, at which fidelity, and where the honest boundaries are.
Everything in the *guaranteed* columns is enforced by CI: exported DXF
is validated by ezdxf (recover + audit, zero errors), exported IFC by
ifcopenshell (including geometry rebuild), and round-trips run against
a 52-file real-world corpus.

Fidelity levels:

- **semantic** — arrives as the editable native concept (an ellipse is
  an ELLIPSE, a block is a BLOCK/INSERT)
- **visual** — looks identical, arrives as exploded primitives
- **—** — not carried by that format

## DXF (AutoCAD, BricsCAD, LibreCAD, Rhino, QCAD, ...)

Writer: hand-written DXF **R2000 (AC1015)**, `$INSUNITS` set from
document units. Reader: ASCII DXF, R12 through current.

| Modulor entity | export → DXF | import ← DXF |
|---|---|---|
| line | LINE (semantic) | semantic |
| polyline | LWPOLYLINE (semantic) | semantic (incl. arc bulges, POLYLINE/VERTEX) |
| circle / arc | CIRCLE / ARC (semantic) | semantic |
| ellipse | ELLIPSE (semantic) | semantic (full); elliptical arcs discretize (visual) |
| spline | SPLINE with fit points (semantic) | semantic (fit points; control-point-only splines approximate) |
| region | solid HATCH + boundary (semantic) | HATCH boundary loops → region (semantic) |
| hatch | HATCH, user-defined pattern / solid (semantic) | region (boundary preserved; pattern not reconstructed) |
| text | TEXT (semantic) | semantic (TEXT + MTEXT, formatting stripped) |
| dim / dim_angular / dim_radial | associative DIMENSION + rendered `*D` block (semantic) | rendered block expands (visual) |
| leader | LEADER + TEXT (semantic) | polyline + text (visual) |
| **block / instance** | **BLOCK / INSERT (semantic)** | **document block + instance (semantic)**; non-uniform or mirrored INSERTs expand (visual); `blocks="explode"` opts out |
| wall / grid / room | exploded primitives + solid HATCH footprint (visual — no DXF concept exists) | n/a |
| solid (3D) | — (use glTF/OBJ/STL/IFC) | — (ACIS blobs counted in `skipped`) |

Layers always carry over with nearest-ACI colors, both directions.
Unsupported input entities are **counted in `skipped`, never silently
dropped**.

## IFC4 (Revit, Archicad, Solibri, BIM checkers)

Export only, semantic BIM: walls become IfcWall with real
IfcOpeningElement voids, levels become storeys, grids become IfcGrid,
rooms become IfcSpace with area quantities, other solids become
tessellated proxies with materials. Block instances export as their
expanded children with deterministic GUIDs. Validated in CI with
ifcopenshell including geometry rebuild.

## glTF / OBJ / STL (SketchUp, Blender, viewers, 3D printing)

Mesh-level (visual by design): solids and walls as triangle meshes,
named per entity (tag or id), with materials (glTF: PBR; OBJ: MTL).
Block instances expand to their children. glTF is Y-up, meters, as the
spec requires.

## Honest boundaries

- **No DWG.** Proprietary; the only practical route is the ODA SDK
  (licensing). Every AutoCAD reads/writes DXF natively — use that.
- **No NURBS surfaces / STEP.** The kernel is a mesh kernel
  (manifold3d). Curves export exactly (ellipses) or as fit-point
  splines; *surfaces* interchange as meshes, not B-rep. Precision
  mechanical workflows that require STEP are out of scope for the core.
- **Dimensions import as graphics.** A DXF DIMENSION arrives as its
  rendered block (visually exact); it does not become a live Modulor
  dim entity. Exported dimensions *are* associative in AutoCAD.
- **Instance limits.** Modulor instances are uniform-scale by design;
  non-uniform or mirrored INSERTs fall back to expanded copies (with a
  warning), never to a wrong transform.
