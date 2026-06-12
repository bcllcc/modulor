"""IFC4 export validation.

The exporter is hand-written SPF; ifcopenshell (dev dependency) is the
independent anchor: it parses the file with a real IFC toolkit and builds
actual geometry from it. If ifcopenshell is unavailable on a platform the
deep checks skip, but the structural self-checks always run.
"""

import pytest

from modulor import Cad


def _build(tmp_path) -> tuple[str, "Cad"]:
    cad = Cad(str(tmp_path / "m.json"))
    cad("add_level", name="L1", elevation=0, height=3500)
    cad("add_level", name="L2", elevation=3500, height=3500)
    cad("add_material", name="concrete", color="#c9c5bd")
    cad("add_wall", path=[[0, 0], [8000, 0], [8000, 5000], [0, 5000], [0, 0]],
        thickness=240, height=3500, tag="ext", material="concrete")
    cad("add_opening", wall={"tags": ["ext"]}, along=1500, width=1000,
        type="door")
    cad("add_opening", wall={"tags": ["ext"]}, along=6000, width=1800,
        type="window")
    cad("add_grid", x=[0, 4000, 8000], y=[0, 5000])
    cad("add_room", name="LIVING", level="L1",
        points=[[0, 0], [5000, 0], [5000, 5000], [0, 5000]])
    cad("add_box", at=[1000, 1000, 0], size=[400, 400, 3500],
        material="concrete", tag="col")
    cad("add_box", at=[1000, 1000, 3500], size=[400, 400, 3500],
        material="concrete", tag="col2")  # second storey by elevation
    path = str(tmp_path / "model.ifc")
    r = cad("export", path=path)
    return path, r


def test_ifc_export_structure(tmp_path):
    path, r = _build(tmp_path)
    assert r["schema"] == "IFC4"
    assert r["storeys"] == 2
    assert r["exported"] == {"IfcWall": 1, "IfcOpeningElement": 2,
                             "IfcGrid": 1, "IfcSpace": 1,
                             "IfcBuildingElementProxy": 2}
    text = open(path, encoding="utf-8").read()
    assert text.startswith("ISO-10303-21;")
    assert text.rstrip().endswith("END-ISO-10303-21;")
    assert "FILE_SCHEMA(('IFC4'))" in text
    # deterministic GUIDs: same model exports byte-identical entity ids
    assert text.count("IFCRELVOIDSELEMENT") == 2


def test_ifc_deterministic(tmp_path):
    p1, _ = _build(tmp_path / "a")
    p2, _ = _build(tmp_path / "b")
    strip = lambda s: "\n".join(  # noqa: E731
        ln for ln in s.splitlines() if not ln.startswith(("FILE_NAME",
                                                          "#5=IFCOWNERHISTORY")))
    assert strip(open(p1).read()) == strip(open(p2).read())


def test_ifc_with_ifcopenshell(tmp_path):
    ifcopenshell = pytest.importorskip("ifcopenshell")
    path, _ = _build(tmp_path)
    f = ifcopenshell.open(path)
    assert f.schema == "IFC4"
    assert len(f.by_type("IfcBuildingStorey")) == 2
    wall = f.by_type("IfcWall")[0]
    assert wall.Name == "ext"
    assert len(f.by_type("IfcRelVoidsElement")) == 2

    # storey assignment by elevation: the upper column sits on L2
    by_storey = {}
    for rel in f.by_type("IfcRelContainedInSpatialStructure"):
        by_storey[rel.RelatingStructure.Name] = \
            [e.Name for e in rel.RelatedElements]
    assert "col2" in by_storey.get("L2", []), by_storey
    assert "col" in by_storey.get("L1", [])

    # space with a schedulable area quantity
    q = f.by_type("IfcQuantityArea")[0]
    assert q.AreaValue == pytest.approx(25.0)

    # the geometry kernel can actually build the wall, voids applied
    import ifcopenshell.geom as geom
    import numpy as np
    shape = geom.create_shape(geom.settings(), wall)
    verts = np.array(shape.geometry.verts).reshape(-1, 3)
    assert verts[:, 2].max() == pytest.approx(3.5)   # metres
    assert verts[:, 0].max() == pytest.approx(8.12)  # 8000mm + 240/2
    tris = np.array(shape.geometry.faces).reshape(-1, 3)
    v = 0.0  # signed volume of the produced mesh
    for a, b, c in tris:
        v += np.dot(verts[a], np.cross(verts[b], verts[c])) / 6.0
    full = 26.0 * 0.24 * 3.5  # centerline x thickness x height
    assert abs(v) < full  # openings actually subtracted
    assert abs(v) > full * 0.8


def test_ifc_rejects_empty_semantics(tmp_path):
    from modulor import CadError
    cad = Cad(str(tmp_path / "e.json"))
    cad("add_line", start=[0, 0], end=[100, 0])
    with pytest.raises(CadError, match="IFC"):
        cad("export", path=str(tmp_path / "x.ifc"))
