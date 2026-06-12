# Modulor roadmap

The single source of truth for where this project is going. Updated as
stages complete. Strategy background: Modulor competes on protocol,
format, conformance and cognition share — not feature breadth
(see GOVERNANCE.md for the frozen identity and scope rules).

## Capability boundary

**Core is, permanently**: the agent-native geometry layer — deterministic
geometry + protocol. 2D drafting, 3D modeling, parametric recipes, the
verification loop (measure/validate/render/find/diff), interop
(DXF in/out, SVG, STL, GLB, IFC out).

**Core is not, permanently**: a GUI editor for humans · an LLM host ·
a constraint solver · photoreal rendering · fabrication-grade NURBS/STEP
surfacing · a full BIM authoring platform (MEP/rebar/CDs) · a hosted
service.

**Depth per domain**: architecture to schematic/DD depth (LOD 200–300);
mechanical to prototyping/3D-print grade; freeform to concept-massing
grade (mesh + SDF). Deeper belongs to the professional tools we export
into.

**The elastic boundary** (extensions, not core): domain semantic packs
(modulor-mech is the template), host-application connectors
(SU/Rhino/Revit plugins), intelligent workflows (drawing take-over).
Rule of thumb: deterministic + no LLM + operates on core semantics →
core; otherwise → extension or downstream product.

## Stages

| stage | content | done when | status |
|---|---|---|---|
| 0 Kernel | 71 ops, geometry stack, 4 channels, viewer | five example domains run | ✅ |
| 1 Trustworthy | contract, error registry, fuzzing, real-world DXF corpus, format spec, conformance checker | 64k adversarial commands, zero crashes; interface drift fails CI | ✅ |
| 2 Shipped | PyPI, GitHub+CI, MCP registry, agent packs, plugin mechanism | any agent is one copy-paste away | ✅ ~95% — remainder: 1.0-rc freeze + full governance + OpenSSF badge |
| 3 Seen | launch posts, tutorials, AgentCAD-Bench, first external users | first stranger-filed issue/PR; sustained downloads; bench live | ⬅️ current |
| 4 Self-running ecosystem | third-party extensions and implementations, community governance | someone independently claims "Modulor-compatible"; first extension not written by us | future |
| 5 Commercial probes (optional) | products above the kernel (drawing take-over service, vertical apps) | first revenue; kernel stays MIT | future |

North-star metric shifts at stage 3: from "tests green" to "external
signals" (downloads, stars, stranger issues). The bottleneck stops being
code.

## Stage-3 plan (current)

1. **Week 1 — finish stage 2**: declare the op surface 1.0-rc, complete
   GOVERNANCE (RFC template), apply for the OpenSSF Best Practices badge.
2. **Week 2 — ammunition**: bilingual launch post (the regenerate demo
   GIF, the "Claude draws a floor plan → IFC → Revit" arc,
   `pip install modulor`), 90-second demo video script, tutorial #1.
3. **Week 3 — launch**: Show HN + Chinese channels (Zhihu/Jike/Bilibili)
   on the same day; fast-response issue duty for a week.
4. **Week 4 — AgentCAD-Bench**: design-brief → model tasks, auto-scored
   by the verification ops; the eval that teaches labs to speak Modulor.

## User journeys (today)

- **Claude Code users**: `/plugin marketplace add bcllcc/modulor` →
  `/plugin install modulor@modulor` → just ask for drawings.
- **Agent builders**: `pip install modulor` + integrations/
  (tool-definitions.json for function calling, `modulor mcp` for MCP,
  one-function adapters for LangChain/AutoGen/CrewAI).
- **Architects/engineers exploring**: run an example, watch it grow in
  `modulor serve`, download the DXF/IFC into familiar tools.
