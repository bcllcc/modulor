"""RFC #1 baseline ops: ellipse, hatch, leader, torus, blocks.

https://github.com/bcllcc/modulor/issues/1
"""
import json
import math
import os

import pytest

import modulor
from modulor.errors import CadError

pytestmark = []


def make():
    return modulor.Cad(units="mm")


# ---------------------------------------------------------------- ellipse

def test_ellipse_create_area_perimeter():
    cad = make()
    r = cad("add_ellipse", center=[100, 50], rx=800, ry=450, rotation=30)
    assert r["created"] == ["e1"]
    area = cad("measure", kind="area", select="e1")["value"]
    assert abs(area - math.pi * 800 * 450) / (math.pi * 800 * 450) < 0.01
    length = cad("measure", kind="length", select="e1")["value"]
    assert length > 0


def test_ellipse_is_closed_shape():
    cad = make()
    cad("add_ellipse", center=[0, 0], rx=500, ry=300)
    r = cad("extrude", select="e1", height=1000)
    vol = cad("measure", kind="volume", select=r["created"])["value"]
    assert abs(vol - math.pi * 500 * 300 * 1000) / (math.pi * 500 * 300 * 1000) < 0.01
    cad("add_circle", center=[0, 0], radius=100)
    cad("boolean_2d", kind="difference", a="e1", b="e3")


def test_ellipse_transforms():
    cad = make()
    cad("add_ellipse", center=[0, 0], rx=400, ry=200)
    cad("rotate", select="e1", angle=90, center=[0, 0])
    ent = cad.doc.entities["e1"]
    assert abs(ent["rotation"] - 90) < 1e-6
    cad("scale", select="e1", factor=2, center=[0, 0])
    assert abs(ent["rx"] - 800) < 1e-6 and abs(ent["ry"] - 400) < 1e-6
    cad("mirror", select="e1", p1=[0, 0], p2=[0, 100])  # must not raise


def test_ellipse_degenerate():
    cad = make()
    with pytest.raises(CadError) as e:
        cad("add_ellipse", center=[0, 0], rx=0, ry=100)
    assert e.value.code == "degenerate"


# ---------------------------------------------------------------- hatch

def test_hatch_patterns_and_budget():
    cad = make()
    cad("add_rect", at=[0, 0], width=1000, height=600)
    r = cad("add_hatch", boundary="e1", pattern="lines", angle=45)
    assert r["lines"] > 0
    r2 = cad("add_hatch", boundary="e1", pattern="cross")
    assert r2["lines"] > r["lines"]
    r3 = cad("add_hatch", boundary="e1", pattern="solid")
    assert r3["lines"] == 0
    with pytest.raises(CadError) as e:
        cad("add_hatch", boundary="e1", spacing=0.001)
    assert e.value.code == "over_budget"


def test_hatch_respects_holes():
    cad = make()
    cad("add_rect", at=[0, 0], width=1000, height=1000)
    cad("add_circle", center=[500, 500], radius=300)
    cad("boolean_2d", kind="difference", a="e1", b="e2")  # -> e3 region
    hatch_id = cad("add_hatch", boundary="e3", spacing=50)["created"][0]
    area = cad("measure", kind="area", select=hatch_id)["value"]
    expected = 1000 * 1000 - math.pi * 300 ** 2
    assert abs(area - expected) / expected < 0.01
    # no hatch line may pass through the hole center
    from modulor import geometry as g
    ent = cad.doc.entities[hatch_id]
    for seg in g.hatch_lines(ent["contours"], ent["spacing"], ent["angle"]):
        (x0, y0), (x1, y1) = seg
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        # segment midpoints that fall inside the hole would be wrong;
        # allow boundary contact within one spacing of the rim
        d = math.hypot(mx - 500, my - 500)
        assert d > 300 - 50 or math.hypot(x1 - x0, y1 - y0) < 2 * 300


def test_hatch_scales_with_entity():
    cad = make()
    cad("add_rect", at=[0, 0], width=400, height=400)
    hid = cad("add_hatch", boundary="e1", spacing=40)["created"][0]
    cad("scale", select=hid, factor=2, center=[0, 0])
    assert abs(cad.doc.entities[hid]["spacing"] - 80) < 1e-9


# ---------------------------------------------------------------- leader

def test_leader_create_and_defaults():
    cad = make()
    r = cad("add_leader", points=[[0, 0], [500, 500], [900, 500]],
            text="waterproofing")
    eid = r["created"][0]
    ent = cad.doc.entities[eid]
    assert ent["height"] == 250.0  # mm document
    assert ent["layer"] == "dims"
    from modulor.render import flatten
    prims = flatten.display_list(cad.doc, [eid])
    kinds = {p["kind"] for p in prims}
    assert {"stroke", "fill", "text"} <= kinds  # line + arrowhead + text


def test_leader_errors():
    cad = make()
    with pytest.raises(CadError):
        cad("add_leader", points=[[0, 0]], text="x")
    with pytest.raises(CadError):
        cad("add_leader", points=[[0, 0], [0, 0]], text="x")


# ---------------------------------------------------------------- torus

def test_torus_volume():
    cad = make()
    r = cad("add_torus", at=[10, 20, 30], radius=400, tube_radius=80)
    expected = 2 * math.pi ** 2 * 400 * 80 ** 2
    assert abs(r["volume"] - expected) / expected < 0.01
    box = r["bbox"]
    assert abs((box["max"][0] - box["min"][0]) - 960) < 5  # 2*(R+r)
    assert abs((box["max"][2] - box["min"][2]) - 160) < 5  # 2*r


def test_torus_degenerate():
    cad = make()
    with pytest.raises(CadError) as e:
        cad("add_torus", radius=100, tube_radius=100)
    assert e.value.code == "degenerate"


# ---------------------------------------------------------------- blocks

def window_doc():
    cad = make()
    cad("add_rect", at=[0, 0], width=900, height=100, tag="win")
    cad("add_line", start=[0, 50], end=[900, 50], tag="win")
    return cad


def test_define_block_replace_keeps_geometry():
    cad = window_doc()
    before = cad("measure", kind="bbox", select="all")["size"]
    r = cad("define_block", select={"tags": ["win"]}, name="win-900")
    assert r["count"] == 2 and len(r["created"]) == 1
    assert cad.doc.entities[r["created"][0]]["type"] == "instance"
    after = cad("measure", kind="bbox", select="all")["size"]
    assert before == after


def test_define_block_no_replace():
    cad = window_doc()
    r = cad("define_block", select={"tags": ["win"]}, name="w", replace=False)
    assert r["created"] == []
    assert {e["type"] for e in cad.doc.entities.values()} == {"polyline", "line"}


def test_block_errors():
    cad = window_doc()
    cad("define_block", select={"tags": ["win"]}, name="w")
    with pytest.raises(CadError):  # duplicate name
        cad("define_block", select="all", name="w")
    with pytest.raises(CadError) as e:
        cad("insert_block", name="missing", at=[0, 0])
    assert e.value.code == "not_found"
    with pytest.raises(CadError):
        cad("insert_block", name="w", at=[0, 0], scale=-1)
    cad("add_grid", x=[0, 5000], y=[0, 5000])
    with pytest.raises(CadError) as e:
        cad("define_block", select={"types": ["grid"]}, name="g")
    assert e.value.code == "bad_type"


def test_insert_scale_rotation_geometry():
    cad = window_doc()
    cad("define_block", select={"tags": ["win"]}, name="w")
    i2 = cad("insert_block", name="w", at=[5000, 0], scale=2)["created"][0]
    a1 = cad("measure", kind="area", select={"types": ["instance"]})["value"]
    assert abs(a1 - 90000 - 360000) < 1  # original + scale^2
    i3 = cad("insert_block", name="w", at=[0, 5000], rotation=90)["created"][0]
    box = cad("measure", kind="bbox", select=i3)["size"]
    assert abs(box[0] - 100) < 1e-6 and abs(box[1] - 900) < 1e-6
    assert i2 != i3


def test_nested_blocks_and_transforms():
    cad = window_doc()
    cad("define_block", select={"tags": ["win"]}, name="w")
    cad("insert_block", name="w", at=[0, 0])
    cad("insert_block", name="w", at=[1200, 0])
    cad("define_block", select={"types": ["instance"]}, name="pair")
    ins = cad("insert_block", name="pair", at=[0, 3000])["created"][0]
    area = cad("measure", kind="area", select=ins)["value"]
    assert abs(area - 2 * 90000) < 1
    cad("move", select=ins, by=[100, 0])
    cad("rotate", select=ins, angle=45, center=[0, 0])
    n = len(cad("array", select=ins, kind="grid", nx=3, ny=2,
                dx=3000, dy=2000)["created"])
    assert n == 5
    with pytest.raises(CadError) as e:
        cad("mirror", select=ins, p1=[0, 0], p2=[0, 1])
    assert e.value.code == "bad_type"


def test_blocks_save_load_schema(tmp_path):
    cad = window_doc()
    cad("define_block", select={"tags": ["win"]}, name="w")
    cad("insert_block", name="w", at=[3000, 0], rotation=15, scale=1.5)
    p = os.path.join(tmp_path, "doc.json")
    cad.save(p)
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.load(open(
        os.path.join(os.path.dirname(modulor.__file__),
                     "document.schema.json"), encoding="utf-8"))
    jsonschema.validate(json.load(open(p, encoding="utf-8")), schema)
    cad2 = modulor.Cad(path=p)
    assert cad2.doc.blocks.keys() == cad.doc.blocks.keys()
    assert (cad2("measure", kind="bbox", select="all")["size"] ==
            cad("measure", kind="bbox", select="all")["size"])
    assert "w" in cad2("doc_info")["blocks"]


def test_blocks_dxf_native_roundtrip(tmp_path):
    cad = window_doc()
    cad("define_block", select={"tags": ["win"]}, name="win-900")
    cad("insert_block", name="win-900", at=[3000, 0], rotation=90)
    cad("insert_block", name="win-900", at=[6000, 0], scale=2)
    p = os.path.join(tmp_path, "blocks.dxf")
    out = cad("export", path=p)
    assert out["blocks"] == ["win-900"]
    assert out["entities"] == 3  # three INSERTs, nothing exploded
    text = open(p, encoding="ascii").read()
    assert "BLOCKS" in text and text.count("INSERT") == 3
    cad2 = make()
    cad2("import_dxf", path=p)
    assert (cad2("measure", kind="bbox", select="all")["size"] ==
            cad("measure", kind="bbox", select="all")["size"])


def test_block_with_solid_renders_and_measures(tmp_path):
    cad = make()
    cad("add_box", at=[0, 0, 0], size=[500, 500, 500], tag="cube")
    cad("define_block", select={"tags": ["cube"]}, name="unit")
    ins = cad("insert_block", name="unit", at=[2000, 2000],
              scale=1.5)["created"][0]
    vol = cad("measure", kind="volume", select=ins)["value"]
    assert abs(vol - 500 ** 3 * 1.5 ** 3) < 1
    png = os.path.join(tmp_path, "i.png")
    cad("export", path=png)
    assert os.path.getsize(png) > 0
    glb = os.path.join(tmp_path, "i.glb")
    cad("export", path=glb)
    assert os.path.getsize(glb) > 0


def test_instance_validate_and_broken_reference():
    cad = window_doc()
    cad("define_block", select={"tags": ["win"]}, name="w")
    cad("insert_block", name="w", at=[0, 0])
    assert cad("validate")["valid"]
    # simulate a hand-edited document with a dangling block reference
    cad.doc.entities["e9"] = {"type": "instance", "layer": "0",
                              "block": "ghost", "at": [0, 0],
                              "rotation": 0.0, "scale": 1.0}
    cad.doc._counter = 9
    problems = cad("validate")["problems"]
    assert any(p["code"] == "not_found" for p in problems)
