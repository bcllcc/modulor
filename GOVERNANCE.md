# Modulor governance

## 0. Identity (frozen)

These identifiers are permanent. They are already in public package
indexes, documents and agent tooling; changing any of them would be a
breaking event for the whole ecosystem and will not happen.

| identifier | value | status |
|---|---|---|
| Project name | **Modulor** (Chinese: 模度) | frozen |
| Python package | `modulor` (PyPI) | frozen |
| CLI command | `modulor` | frozen |
| MCP server name | `modulor` | frozen |
| Document format id | **`modulor/1`** | frozen |
| Legacy format id | `nativecad/1` — readable forever, never written | frozen |
| Op contract id | `modulor-ops/1` | frozen |
| Repository | github.com/bcllcc/modulor | current home |

## 1. Modulor Standard vs Modulor Core

**Modulor Standard** is the specification. It is what third parties
implement and what conformance is measured against:

- the op protocol: [docs/API.md](docs/API.md) +
  machine contract [docs/api.json](docs/api.json)
- the document format: [docs/FORMAT.md](docs/FORMAT.md) +
  [docs/document.schema.json](docs/document.schema.json)
- the error taxonomy (`ERROR_CODES`, shipped inside the contract)
- the API laws (AGENT_GUIDE.md §3.5) and the conventions in FORMAT.md

**Modulor Core** is the reference implementation: the `modulor` Python
package. It is *canonical, not exclusive* — anyone may reimplement the
Standard in any language. The promise of Core is that it always conforms
to the Standard exactly (enforced by the contract tests), so other
implementations validate themselves against it and against
`modulor check --strict`.

A change to Core that alters observable protocol or format behavior is by
definition a change to the Standard, and follows the rules below.

## 2. Versioning and compatibility

**The op surface was declared 1.0-rc on 2026-06-12** (71 core ops, since
extended to 77 by accepted RFC #1; docs/api.json is authoritative). From
that point:

- breaking changes to ops, the document format or the error registry
  require an **accepted RFC** (see §3) and ship only in a major version,
  preceded by a deprecation in a minor version;
- additive changes (new optional params, new ops, new optional format
  fields, new error codes) also pass through an RFC when they extend the
  Standard, but may ship in minor versions;
- Core follows **semver**; the contract (`scripts/api_dump.py` output)
  is regenerated and committed together with any interface change.
- The document format evolves additively within `modulor/1` (new optional
  fields, new entity types). Field meaning changes require `modulor/2`
  plus a migration path. Readers must ignore unknown optional fields and
  may skip unknown entity types — counting them, never silently mutating.
- Error codes are a closed registry; additions are contract changes.

## 3. Change process (RFC)

- Routine changes (bug fixes, internals, docs, performance): PR + the
  contract test gate (interface drift fails CI).
- **Standard-level changes** (ops, format, error codes, API laws): open
  an issue with the *RFC: Standard change* template **before
  implementing**. An RFC states motivation, the exact contract diff,
  compatibility impact and the extension-instead alternative.
- An RFC is *accepted* when a maintainer labels it `rfc-accepted` after
  open discussion (minimum 72h for breaking changes). Implementation
  PRs link the RFC and carry the regenerated contract in the same
  commit.
- Maintainers' own Standard changes follow the same process — no
  shortcuts.

## 4. Scope rule

Core accepts **deterministic geometry and protocol** only. No LLM calls,
no heuristic recognizers, no host-application plugins inside Core —
those live in extensions and downstream products. Domain semantics added
in the future go to extension packages, not Core.
