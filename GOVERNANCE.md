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

- Core follows **semver**. Pre-1.0: breaking changes are allowed but
  always recorded in the contract (`scripts/api_dump.py`, committed
  together with the code). From 1.0: breaking op/format changes only in
  major versions, with deprecation first.
- The document format evolves additively within `modulor/1` (new optional
  fields, new entity types). Field meaning changes require `modulor/2`
  plus a migration path. Readers must ignore unknown optional fields and
  may skip unknown entity types — counting them, never silently mutating.
- Error codes are a closed registry; additions are contract changes.

## 3. Change process

- Routine changes: PR + the contract test gate (interface drift fails CI).
- Standard-level changes (new ops, format fields, error codes, law
  changes): open an issue tagged `rfc` describing motivation, the exact
  contract diff, and compatibility impact, before implementation.

## 4. Scope rule

Core accepts **deterministic geometry and protocol** only. No LLM calls,
no heuristic recognizers, no host-application plugins inside Core —
those live in extensions and downstream products. Domain semantics added
in the future go to extension packages, not Core.
