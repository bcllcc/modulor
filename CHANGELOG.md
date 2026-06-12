# Changelog

## 1.0.0rc3 — 2026-06-13

**Interoperability is now a contract** (RFC #2, accepted):
docs/INTEROP.md states per-format fidelity guarantees, enforced in CI.

- DXF writer rewritten: R12 → **R2000 (AC1015)**, semantic output —
  ellipse → ELLIPSE, spline → SPLINE (fit points), hatch → HATCH
  (user-defined pattern / solid), dims → associative DIMENSION with
  rendered `*D` blocks, leader → LEADER, polyline → LWPOLYLINE,
  region/wall footprints → solid HATCH + boundary; `$INSUNITS` from
  document units. ezdxf recover + audit: zero errors, zero fixes.
- import_dxf: named blocks become **document blocks + instances**
  (new `blocks` param, default `"native"`; `"explode"` restores flat
  copies). Non-uniform/mirrored INSERTs still expand, with a warning.
  Full ELLIPSEs import as native ellipses; LEADER now imported.
- IFC: block instances export as their expanded children with
  deterministic GUIDs (walls stay IfcWall, solids stay proxies).
- ezdxf joins the dev extras as the DXF referee in CI (test-only,
  runtime dependencies remain numpy + manifold3d).

## 1.0.0rc2 — 2026-06-12

**The drafting/modeling baseline is complete** (RFC #1, accepted): six
additive ops, 71 → 77. No breaking changes; every existing document and
agent integration keeps working.

- `add_ellipse`, `add_hatch` (lines/cross/solid, hole-aware, re-clips
  on regenerate), `add_leader` (arrow + text annotation), `add_torus`
- **blocks**: `define_block` + `insert_block` — reusable components
  with position/rotation/uniform scale. Instances work everywhere via
  expansion (render, measure, booleans, transforms, arrays) and export
  to DXF as native BLOCKS/INSERT (round-trips through our importer).
  Format: optional top-level `blocks` map + `instance` entity (schema
  updated, additive)
- `add_cone` was *not* added: `add_cylinder(radius_top=0)` already
  covers cones/frustums
- hardening found by the extended fuzz campaign: `segments` budgets on
  cylinder/sphere/revolve/torus (adversarial values could hang the
  kernel), `add_grid` label-type validation
- lint: ruff (incl. flake8-bandit security rules) clean and enforced
  in CI; OpenSSF Best Practices badge (passing, project 13175)

## 1.0.0rc1 — 2026-06-12

**The op surface is frozen.** From this release, breaking changes to
ops, the document format or the error registry require an accepted RFC
and a deprecation cycle (GOVERNANCE.md). 71 core ops, contract-tested.

- governance: RFC process and issue templates; CONTRIBUTING, SECURITY,
  release-hygiene guard
- everything below is included

## 0.7.x — extension mechanism

- entry-point plugins with structural namespacing (`mech.gear`),
  collision rejection, load-failure isolation, `check_laws` conformance
- official template extension: modulor-mech (involute spur gears)
- `modulor plugins` CLI (diagnostics + law check); Standard/extension
  boundary enforced across api.json, API.md, tool definitions
- core contract excludes plugins (tested)

## 0.6.x — BIM bridge + agent packs

- semantic IFC4 export: walls with real openings, storeys from levels,
  grids, rooms as spaces with area quantities, tessellated proxies,
  materials; validated against ifcopenshell including geometry rebuild
- agent packs: Claude Code plugin marketplace (one-command install),
  MCP official registry listing (auto-published per release), Cursor/
  Codex artifacts, OpenAI-format tool definitions, CI-executed cookbook,
  runnable LangChain/AutoGen/CrewAI demos, Chinese onboarding
- fifth showcase example: urban massing

## 0.5.x — public release

- renamed NativeCAD → Modulor; format id `modulor/1` (legacy readable)
- published to PyPI + GitHub with clean history; CI matrix
  (3 OS × 2 Python); trusted publishing
- real-world DXF corpus (52 files) and the importer upgrades it forced:
  INSERT blocks (nested/arrays), DIMENSION blocks, HATCH boundaries,
  legacy codepages (GBK etc.), unicode escapes

## 0.4.x — parametrics, semantics, audit

- parametric recipes: expressions in any numeric field, params/levels/
  grids, `recipe_set` + `regenerate`, design `diff`
- architectural semantics: grid/level/room/program/roof/stair/facade;
  freeform completion: `add_surface` height-field slabs
- deep API audit: 22-code error registry enforced at construction, 100%
  param/returns docs, result-key unification (created/modified), effects
  metadata, resource budgets, finite-number validation, behavioral
  fuzzer (64k commands, 8 seeds, zero crashes), format spec
  (FORMAT.md + JSON Schema) and `modulor check --strict`

## 0.3.x — agent feedback + freeform + interop

- labeled renders, spatial `find`, snapshot/restore
- spline/curved walls, loft (vertical spline interpolation), sweep
  (parallel transport), deform (twist/taper/bend), implicit surfaces
  (safe SDF expressions), smooth; fillet/chamfer, angular/radial dims,
  elevation projection, shell
- DXF import (first version); GitHub Actions CI; scale benchmark

## 0.2.0 — live viewer

- `modulor serve`: read-only browser viewer (SVG plan + self-contained
  WebGL orbit view) that live-follows the document file

## 0.1.0 — kernel

- 41 ops over manifold3d: 2D drafting, walls/openings/dims, 3D booleans,
  extrude/revolve, transforms; SVG/DXF/OBJ/STL/GLB exporters; software
  renderer with stroke font; CLI/REPL/MCP/Python channels; atomic
  batches; structured errors
