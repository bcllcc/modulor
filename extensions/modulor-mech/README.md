# modulor-mech

Mechanical engineering ops for [Modulor](https://github.com/bcllcc/modulor),
and the **official template for Modulor extensions**
(see [docs/PLUGINS.md](../../docs/PLUGINS.md)).

```
pip install "modulor-mech @ git+https://github.com/bcllcc/modulor#subdirectory=extensions/modulor-mech"
```

(PyPI release pending — installing from the repo works today.)

then, from any agent or script — the op simply exists:

```json
[{"op": "mech.gear", "module": 2, "teeth": 24, "bore": 8, "tag": "g"},
 {"op": "extrude", "select": {"tags": ["g"]}, "height": 8},
 {"op": "export", "path": "gear.stl"}]
```

## Ops

| op | what |
|---|---|
| `mech.gear` | involute spur gear outline (standard full-depth teeth, 14.5–25° pressure angle, optional bore) as a region — extrude for a solid |

Outputs are ordinary Modulor entities: transformable, boolean-able,
exportable to DXF/SVG/STL/GLB/IFC like anything else.

## As a template

Three things make an extension: an entry point in `pyproject.toml`, a
`register(api)` function, and `assert check_laws("mech") == []` in the
tests. Everything else here is ordinary geometry code.
