"""DXF semantic fidelity (RFC #2): the R2000 writer must produce files
that AutoCAD-class software opens as editable native objects.

ezdxf is the FLOSS referee (same pattern as ifcopenshell for IFC):
recover + audit must report zero errors and zero fixes, and every
Modulor entity must arrive as its native DXF counterpart.
"""
import math
import os

import pytest

import modulor

ezdxf = pytest.importorskip("ezdxf")


def rich_doc():
    cad = modulor.Cad(units="mm")
    cad("add_line", start=[0, 0], end=[5000, 0])
    cad("add_ellipse", center=[2000, 2000], rx=800, ry=450, rotation=30)
    cad("add_spline", points=[[0, 0], [1000, 800], [2500, 0], [1500, -1200]],
        closed=True)
    cad("add_rect", at=[4000, 1000], width=1200, height=900)
    cad("add_hatch", boundary="e4", pattern="cross", angle=45)
    cad("add_hatch", boundary="e2", pattern="solid")
    cad("add_leader", points=[[2000, 2500], [3000, 3500]], text="note")
    cad("add_dim", p1=[0, 0], p2=[5000, 0], offset=-600)
    cad("add_circle", center=[7000, 0], radius=400)
    cad("add_dim_radial", of="e9", direction=30)
    cad("add_dim_angular", center=[0, 0], p1=[500, 0], p2=[400, 400])
    cad("add_text", at=[0, 4000], text="SEMANTIC", height=300)
    cad("add_wall", path=[[0, 6000], [4000, 6000]], thickness=200)
    cad("define_block", select={"types": ["circle"]}, name="knob")
    cad("insert_block", name="knob", at=[9000, 0], rotation=45, scale=2)
    return cad


def export(cad, tmp_path, name="t.dxf"):
    p = os.path.join(tmp_path, name)
    cad("export", path=p)
    return p


def test_audit_is_clean(tmp_path):
    from ezdxf import recover
    p = export(rich_doc(), tmp_path)
    doc, auditor = recover.readfile(p)
    assert doc.dxfversion == "AC1015"
    assert not auditor.errors, [e.message for e in auditor.errors]
    assert not auditor.fixes, [f.message for f in auditor.fixes]
    # strict, non-recovering parser must accept it too
    ezdxf.readfile(p)


def test_native_entity_mapping(tmp_path):
    p = export(rich_doc(), tmp_path)
    doc = ezdxf.readfile(p)
    types = {}
    for e in doc.modelspace():
        types[e.dxftype()] = types.get(e.dxftype(), 0) + 1
    assert types["ELLIPSE"] == 1
    assert types["SPLINE"] == 1
    assert types["HATCH"] == 3        # cross + solid + wall footprint
    assert types["LEADER"] == 1
    assert types["DIMENSION"] == 3    # aligned + radial + angular
    assert types["INSERT"] == 2       # define_block replace + insert_block
    assert types["LWPOLYLINE"] >= 2   # rect + boundaries
    assert "POLYLINE" not in types    # the R12 fallback is gone


def test_ellipse_and_spline_geometry(tmp_path):
    p = export(rich_doc(), tmp_path)
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    el = msp.query("ELLIPSE")[0]
    assert abs(el.dxf.ratio - 450 / 800) < 1e-9
    major = el.dxf.major_axis
    assert abs(math.hypot(major[0], major[1]) - 800) < 1e-6
    assert abs(math.degrees(math.atan2(major[1], major[0])) - 30) < 1e-6
    sp = msp.query("SPLINE")[0]
    assert len(sp.fit_points) == 4 and sp.closed


def test_dimensions_are_associative(tmp_path):
    p = export(rich_doc(), tmp_path)
    doc = ezdxf.readfile(p)
    dims = doc.modelspace().query("DIMENSION")
    kinds = sorted(d.dimtype for d in dims)
    assert kinds == [1, 4, 5]  # aligned, radial, 3-point angular
    for d in dims:
        assert d.dxf.geometry.startswith("*D")   # rendered block attached
        assert d.dxf.geometry in doc.blocks
    aligned = [d for d in dims if d.dimtype == 1][0]
    assert tuple(aligned.dxf.defpoint2)[:2] == (0, 0)
    assert tuple(aligned.dxf.defpoint3)[:2] == (5000, 0)


def test_hatch_pattern_definition(tmp_path):
    p = export(rich_doc(), tmp_path)
    doc = ezdxf.readfile(p)
    hatches = doc.modelspace().query("HATCH")
    cross = [h for h in hatches if h.dxf.pattern_name == "MODULOR"][0]
    assert not cross.dxf.solid_fill
    assert len(cross.pattern.lines) == 2  # 45 and 135 degrees
    solids = [h for h in hatches if h.dxf.solid_fill]
    assert len(solids) == 2


def test_units_declared(tmp_path):
    p = export(rich_doc(), tmp_path)
    doc = ezdxf.readfile(p)
    assert doc.header["$INSUNITS"] == 4  # mm
    cad_m = modulor.Cad(units="m")
    cad_m("add_line", start=[0, 0], end=[5, 0])
    p2 = export(cad_m, tmp_path, "m.dxf")
    assert ezdxf.readfile(p2).header["$INSUNITS"] == 6


def test_own_importer_reads_everything_back(tmp_path):
    cad = rich_doc()
    p = export(cad, tmp_path)
    cad2 = modulor.Cad(units="mm")
    r = cad2("import_dxf", path=p)
    assert r["skipped"] == {}
    assert r.get("blocks") == ["knob"]
    inst = [(e["block"], e["rotation"], e["scale"])
            for e in cad2.doc.entities.values() if e["type"] == "instance"]
    assert ("knob", 45.0, 2.0) in inst
    # exact semantic round-trip of the rich types
    el = [e for e in cad2.doc.entities.values() if e["type"] == "ellipse"][0]
    assert (abs(el["rx"] - 800) < 1e-6 and abs(el["ry"] - 450) < 1e-6
            and abs(el["rotation"] % 180 - 30) < 1e-6)
    sp = [e for e in cad2.doc.entities.values() if e["type"] == "spline"][0]
    assert len(sp["points"]) == 4 and sp["closed"]
    # global geometry within tolerance (dimension graphics are heuristic
    # in entity-bbox form but exact prims after the round-trip)
    s1 = cad("measure", kind="bbox", select="all")["size"]
    s2 = cad2("measure", kind="bbox", select="all")["size"]
    diag = math.hypot(s1[0], s1[1])
    assert all(abs(a - b) < diag * 0.05 for a, b in zip(s1, s2))


def test_import_explode_mode(tmp_path):
    p = export(rich_doc(), tmp_path)
    cad = modulor.Cad(units="mm")
    r = cad("import_dxf", path=p, blocks="explode")
    assert "blocks" not in r
    assert not [e for e in cad.doc.entities.values()
                if e["type"] == "instance"]


def test_non_uniform_insert_falls_back(tmp_path):
    # hand-build a DXF with a non-uniform INSERT: must expand, not error
    cad = rich_doc()
    p = export(cad, tmp_path)
    doc = ezdxf.readfile(p)
    ins = doc.modelspace().query("INSERT")[0]
    ins.dxf.xscale = 2.0
    ins.dxf.yscale = 1.0
    p2 = os.path.join(tmp_path, "nonuni.dxf")
    doc.saveas(p2)
    cad2 = modulor.Cad(units="mm")
    r = cad2("import_dxf", path=p2)
    assert r["imported"].get("INSERT", 0) >= 1
    assert cad2("validate")["valid"]
