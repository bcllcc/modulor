# Building Modulor extensions

Core accepts deterministic geometry and protocol only
([GOVERNANCE.md §4](../GOVERNANCE.md)). Domain semantics — gears, rebar,
landscape, robotics — live in **extensions**: separate pip packages that
add namespaced ops without forking anything.

The official template is
[`extensions/modulor-mech`](../extensions/modulor-mech) (an involute
spur gear op). Copy it; the whole mechanism is ~30 lines of your code.

## 1. The mechanics

```toml
# pyproject.toml
[project]
name = "modulor-yourdomain"
dependencies = ["modulor>=0.7"]

[project.entry-points."modulor.plugins"]
yourdomain = "modulor_yourdomain"        # entry-point name = namespace
```

```python
# modulor_yourdomain/__init__.py
def register(api):
    @api.op("thing",                      # callable as yourdomain.thing
            doc="One-line summary agents will read.",
            params={"at": api.P.point2(req=True, doc="position")},
            example={"op": "yourdomain.thing", "at": [0, 0]},
            returns="{created: [id]}")
    def thing(doc, p):
        eid = doc.add_entity("circle", {"center": p["at"], "radius": 1},
                             layer="yourdomain")
        return {"created": [eid]}
```

`pip install` your package and the op exists — in `modulor ops`, in
`help`, in MCP discovery, in batches and recipes. No registration step
for users.

## 2. The rules (enforced, not advisory)

- **Namespace is structural**: the entry-point name prefixes every op
  (`yourdomain.thing`); collisions with core or other plugins are
  rejected at registration.
- **The API laws apply to you**: documented params, declared `returns`
  (`created`/`modified` semantics), declared `effects`, selector naming.
  Put this one line in your test suite — it is the extension conformance
  check:

  ```python
  from modulor.plugins import check_laws
  assert check_laws("yourdomain") == []
  ```

- **Emit ordinary entities.** Extensions add *ops*, never entity types:
  your output must be regions/polylines/solids/etc., so it stays
  transformable, boolean-able and exportable by everything downstream.
- **Determinism.** No LLM calls, no network, no randomness inside ops.
  Smart workflows live a layer above (agents), not inside ops.
- **Isolation contract**: if your `register()` raises, Modulor records
  it (`modulor.plugins.plugin_status()`) and continues without you —
  you can't break the host, and the host won't hide your error.

## 2.5 Security boundary (read this)

Extensions are ordinary Python packages: **installing one means running
its code** at import time, with your user's permissions. The isolation
described above is about *errors*, not security — there is no sandbox.
Treat `pip install modulor-something` with exactly the trust you'd give
any dependency: review it, pin it, prefer known publishers. Agents
should never be allowed to install extensions autonomously.

Diagnostics: `modulor plugins` shows what loaded and what failed;
`modulor plugins <namespace>` runs the API-law conformance check.

## 3. What you inherit for free

Validation and expression support on your params (`"bay*2"` works in
your numeric fields), structured errors, atomic batches, recipe/
regenerate compatibility, fuzz-tested kernel underneath, all exporters,
the viewer, MCP/CLI/Python exposure.

## 4. What stays yours

The core contract (docs/api.json) covers core ops only. Your surface is
yours to version and freeze — ship your own contract file and tests if
you want the same discipline (recommended; copy
`tests/test_mech.py` from the template).
