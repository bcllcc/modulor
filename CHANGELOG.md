# Changelog

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
