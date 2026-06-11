"""Smoke + behavior tests across the whole op surface."""
import json
import math
import os
import struct

import pytest

from modulor import Cad, CadError, run_batch
from modulor.document import Document
from modulor.engine import BatchError


@pytest.fixture
def cad():
    return Cad(units="mm")


# ---------------------------------------------------------------- 2D basics

def test_primitives_and_list(cad):
    cad("add_line", start=[0, 0], end=[100, 0])
    cad("add_polyline", points=[[0, 0], [50, 0], [50, 30]], closed=False)
    cad("add_rect", at=[0, 0], width=40, height=30)
    cad("add_circle", center=[10, 10], radius=5)
    cad("add_arc", center=[0, 0], radius=20, start_angle=0, end_angle=90)
    r = cad("list")
    assert r["count"] == 5


def test_degenerate_rejected(cad):
    with pytest.raises(CadError, match="coincide"):
        cad("add_line", start=[1, 1], end=[1, 1])
    with pytest.raises(CadError):
        cad("add_circle", center=[0, 0], radius=0)


def test_unknown_param_suggests(cad):
    with pytest.raises(CadError, match="strat"):
        cad("add_line", strat=[0, 0], end=[1, 0])


def test_unknown_op_suggests(cad):
    with pytest.raises(CadError) as ei:
        cad("add_circl", center=[0, 0], radius=5)
    assert "add_circle" in ei.value.hint


def test_measure_area_circle(cad):
    cad("add_circle", center=[0, 0], radius=10, tag="c")
    a = cad("measure", kind="area", select={"tags": ["c"]})["value"]
    assert a == pytest.approx(math.pi * 100, rel=0.01)


def test_boolean_2d_difference(cad):
    cad("add_rect", at=[0, 0], width=100, height=100, tag="plate")
    cad("add_circle", center=[50, 50], radius=10, tag="hole")
    r = cad("boolean_2d", kind="difference", a={"tags": ["plate"]},
            b={"tags": ["hole"]})
    assert r["area"] == pytest.approx(10000 - math.pi * 100, rel=0.01)
    assert cad("list")["count"] == 1  # inputs consumed


def test_offset_roundtrip(cad):
    cad("add_rect", at=[0, 0], width=100, height=100, tag="r")
    out = cad("offset", select={"tags": ["r"]}, delta=10)["created"]
    a = cad("measure", kind="area", select=out)["value"]
    assert a == pytest.approx(120 * 120, rel=0.01)


# ---------------------------------------------------------------- transforms

def test_move_rotate_scale(cad):
    cad("add_rect", at=[0, 0], width=10, height=10, tag="r")
    cad("move", select={"tags": ["r"]}, by=[100, 0])
    bb = cad("measure", kind="bbox", select={"tags": ["r"]})
    assert bb["bbox"]["min"][0] == pytest.approx(100)
    cad("rotate", select={"tags": ["r"]}, angle=45, center=[105, 5])
    cad("scale", select={"tags": ["r"]}, factor=2, center=[105, 5])
    a = cad("measure", kind="area", select={"tags": ["r"]})["value"]
    assert a == pytest.approx(400, rel=0.01)


def test_copy_and_array(cad):
    cad("add_circle", center=[0, 0], radius=5, tag="c")
    assert len(cad("copy", select={"tags": ["c"]}, by=[20, 0], count=3)["created"]) == 3
    cad2 = Cad(units="mm")
    cad2("add_circle", center=[10, 0], radius=2, tag="c")
    made = cad2("array", select={"tags": ["c"]}, kind="polar", count=6,
                center=[0, 0])["created"]
    assert len(made) == 5


def test_mirror_copy(cad):
    cad("add_rect", at=[10, 0], width=10, height=10, tag="r")
    r = cad("mirror", select={"tags": ["r"]}, p1=[0, 0], p2=[0, 1], copy=True)
    bb = cad("measure", kind="bbox", select=r["created"])
    assert bb["bbox"]["max"][0] == pytest.approx(-10)


def test_circle_non_uniform_scale_rejected(cad):
    cad("add_circle", center=[0, 0], radius=5)
    with pytest.raises(CadError, match="uniform"):
        cad("scale", select="all", factor=[2, 3])


# ---------------------------------------------------------------- walls

def test_wall_open_and_openings(cad):
    r = cad("add_wall", path=[[0, 0], [5000, 0]], thickness=200, tag="w")
    assert r["length"] == 5000
    cad("add_opening", wall={"tags": ["w"]}, along=2500, width=1000,
        type="door")
    area = cad("measure", kind="area", select={"tags": ["w"]})["value"]
    assert area == pytest.approx(5000 * 200 - 1000 * 200, rel=0.02)


def test_wall_closed_ring(cad):
    cad("add_wall", path=[[0, 0], [4000, 0], [4000, 3000], [0, 3000], [0, 0]],
        thickness=200, tag="ring")
    area = cad("measure", kind="area", select={"tags": ["ring"]})["value"]
    # outer 4200x3200 minus inner 3800x2800 = centerline perimeter x thickness
    assert area == pytest.approx(14000 * 200, rel=0.001)
    vol = cad("measure", kind="volume", select={"tags": ["ring"]})["value"]
    assert vol > 0


def test_opening_outside_wall_rejected(cad):
    cad("add_wall", path=[[0, 0], [1000, 0]], thickness=100, tag="w")
    with pytest.raises(CadError, match="outside"):
        cad("add_opening", wall={"tags": ["w"]}, along=5000, width=500)


# ---------------------------------------------------------------- 3D

def test_box_volume(cad):
    r = cad("add_box", at=[0, 0, 0], size=[10, 20, 30])
    assert r["volume"] == pytest.approx(6000)


def test_extrude_and_boolean(cad):
    cad("add_rect", at=[0, 0], width=50, height=50, tag="p")
    body = cad("extrude", select={"tags": ["p"]}, height=10, tag="body")
    assert body["volume"] == pytest.approx(25000)
    cad("add_cylinder", at=[25, 25, -5], radius=5, height=20, tag="drill")
    r = cad("boolean_3d", kind="difference", a={"tags": ["body"]},
            b={"tags": ["drill"]})
    assert r["volume"] == pytest.approx(25000 - math.pi * 25 * 10, rel=0.01)


def test_revolve(cad):
    # a 10x10 square from x=20..30 revolved fully around x=0:
    # volume = 2*pi*R_centroid*A = 2*pi*25*100 (Pappus)
    cad("add_rect", at=[20, 0], width=10, height=10, tag="p")
    r = cad("revolve", select={"tags": ["p"]}, segments=256)
    vol = cad("measure", kind="volume", select=r["created"])["value"]
    assert vol == pytest.approx(2 * math.pi * 25 * 100, rel=0.01)


def test_revolve_across_axis_rejected(cad):
    cad("add_rect", at=[-5, 0], width=10, height=10)
    with pytest.raises(CadError, match="axis"):
        cad("revolve", select="all")


def test_slice_and_project(cad):
    cad("add_cylinder", at=[0, 0, 0], radius=10, height=20, segments=64)
    sl = cad("slice", select="all", z=10)
    a = cad("measure", kind="area", select=sl["created"])["value"]
    assert a == pytest.approx(math.pi * 100, rel=0.02)
    pr = cad("project", select={"types": ["solid"]})
    a2 = cad("measure", kind="area", select=pr["created"])["value"]
    assert a2 == pytest.approx(math.pi * 100, rel=0.02)


def test_solidify_wall(cad):
    cad("add_wall", path=[[0, 0], [1000, 0]], thickness=100, height=2000, tag="w")
    r = cad("solidify", select={"tags": ["w"]})
    ent = cad("get", id=r["created"][0])["entity"]
    assert ent["type"] == "solid"
    assert cad("measure", kind="volume", select=r["created"])["value"] == \
        pytest.approx(1000 * 100 * 2000)


# ---------------------------------------------------------------- persistence

def test_save_load_roundtrip(tmp_path):
    p = str(tmp_path / "doc.json")
    cad = Cad(p)
    cad("add_wall", path=[[0, 0], [3000, 0]], thickness=150, tag="w")
    cad("add_box", at=[0, 0, 0], size=[100, 100, 100])
    cad.save()
    cad2 = Cad(p)
    assert cad2("list")["count"] == 2
    assert cad2("measure", kind="volume", select={"types": ["solid"]})["value"] \
        == pytest.approx(1e6)


def test_batch_atomicity(tmp_path):
    p = str(tmp_path / "doc.json")
    doc = Document.open_or_create(p)
    with pytest.raises(BatchError) as ei:
        run_batch(doc, [
            {"op": "add_circle", "center": [0, 0], "radius": 5},
            {"op": "add_circle", "center": [0, 0], "radius": -1},
        ])
    assert ei.value.index == 1
    assert len(ei.value.results) == 1


# ---------------------------------------------------------------- exports

def test_exports(tmp_path):
    cad = Cad(units="mm")
    cad("add_wall", path=[[0, 0], [2000, 0]], thickness=100, tag="w")
    cad("add_dim", p1=[0, 0], p2=[2000, 0], offset=-300)
    cad("add_text", at=[0, 500], text="TEST 123")
    cad("add_box", at=[0, 0, 0], size=[500, 500, 500], tag="b")

    svg = str(tmp_path / "t.svg")
    cad("export", path=svg)
    content = open(svg, encoding="utf-8").read()
    assert content.startswith("<svg") and "TEST 123" in content

    dxf = str(tmp_path / "t.dxf")
    cad("export", path=dxf)
    txt = open(dxf, encoding="ascii").read()
    assert "AC1009" in txt and "EOF" in txt

    stl = str(tmp_path / "t.stl")
    cad("export", path=stl)
    with open(stl, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
    assert n > 0 and os.path.getsize(stl) == 84 + n * 50

    glb = str(tmp_path / "t.glb")
    cad("export", path=glb)
    with open(glb, "rb") as f:
        magic, ver, _ = struct.unpack("<III", f.read(12))
    assert magic == 0x46546C67 and ver == 2

    obj = str(tmp_path / "t.obj")
    cad("export", path=obj)
    assert "v " in open(obj, encoding="ascii").read()

    png2d = str(tmp_path / "plan.png")
    cad("render", path=png2d, mode="plan")
    assert open(png2d, "rb").read(8) == b"\x89PNG\r\n\x1a\n"

    png3d = str(tmp_path / "iso.png")
    cad("render", path=png3d, mode="shaded", camera="iso")
    assert open(png3d, "rb").read(8) == b"\x89PNG\r\n\x1a\n"


def test_export_json_copy(tmp_path, cad):
    cad("add_circle", center=[0, 0], radius=5)
    out = str(tmp_path / "copy.json")
    cad("export", path=out)
    d = json.load(open(out, encoding="utf-8"))
    assert d["format"] == "modulor/1" and len(d["entities"]) == 1


# ---------------------------------------------------------------- discovery

def test_help_lists_and_describes(cad):
    all_ops = cad("help")
    assert any(o["op"] == "add_wall" for o in all_ops["ops"])
    one = cad("help", name="extrude")
    assert "height" in one["params"] and one["params"]["height"]["required"]


def test_validate_flags_problems(cad):
    cad("add_circle", center=[0, 0], radius=5)
    cad.doc.entities["e1"]["radius"] = -1  # corrupt it behind the API
    r = cad("validate")
    assert not r["valid"] and r["problems"][0]["id"] == "e1"


# ---------------------------------------------------------------- M1 feedback

def test_find_spatial(cad):
    cad("add_circle", center=[0, 0], radius=10, tag="near")
    cad("add_circle", center=[500, 0], radius=10, tag="far")
    r = cad("find", at=[0, 0], radius=100)
    assert [e["tag"] for e in r["found"]] == ["near"]
    r2 = cad("find", bbox={"min": [400, -50], "max": [600, 50]})
    assert [e["tag"] for e in r2["found"]] == ["far"]


def test_snapshot_restore(tmp_path):
    cad = Cad(str(tmp_path / "d.json"))
    cad("add_circle", center=[0, 0], radius=5)
    cad.save()
    cad("snapshot", name="s1")
    cad("delete", select="all")
    assert cad("list")["count"] == 0
    cad("restore", name="s1")
    assert cad("list")["count"] == 1
    assert cad("snapshots")["snapshots"][0]["name"] == "s1"


def test_labeled_render(tmp_path, cad):
    cad("add_circle", center=[0, 0], radius=50, tag="c")
    p = str(tmp_path / "lab.png")
    r = cad("render", path=p, mode="plan", labels=True)
    assert r["labels"] and open(p, "rb").read(4)[1:4] == b"PNG"


def test_uppercase_id_tolerated(cad):
    cad("add_circle", center=[0, 0], radius=5)
    assert cad("get", id="E1")["entity"]["type"] == "circle"
    cad("move", select="E1", by=[10, 0])


# ---------------------------------------------------------------- M2 freeform

def test_spline_closed_area(cad):
    cad("add_spline", closed=True, tag="s",
        points=[[10, 0], [0, 10], [-10, 0], [0, -10]])
    a = cad("measure", kind="area", select={"tags": ["s"]})["value"]
    assert 200 < a < 320  # smooth oval: bigger than the diamond (200)


def test_curved_wall(cad):
    r = cad("add_wall", path=[[0, 0], [2000, 800], [4000, 0]],
            thickness=200, smooth=True, tag="w")
    assert r["length"] > 4200  # curve is longer than the straight chord run
    assert cad("measure", kind="volume", select={"tags": ["w"]})["value"] > 0


def test_loft_cylinder_approx(cad):
    cad("add_circle", center=[0, 0], radius=10, tag="a")
    cad("add_circle", center=[0, 0], radius=10, tag="b")
    r = cad("loft", sections=[{"select": {"tags": ["a"]}, "z": 0},
                              {"select": {"tags": ["b"]}, "z": 20}],
            samples=128)
    assert r["volume"] == pytest.approx(math.pi * 100 * 20, rel=0.02)


def test_loft_divisions_smooth(cad):
    cad("add_rect", at=[0, 0], width=20, height=20, anchor="center", tag="a")
    cad("add_circle", center=[0, 0], radius=5, tag="b")
    r = cad("loft", sections=[{"select": {"tags": ["a"]}, "z": 0},
                              {"select": {"tags": ["b"]}, "z": 30}],
            samples=48, divisions=8)
    assert r["volume"] > 0


def test_sweep_straight_prism(cad):
    cad("add_circle", center=[0, 0], radius=5, tag="p")
    r = cad("sweep", profile={"tags": ["p"]}, smooth=False, samples=128,
            path=[[0, 0, 0], [0, 0, 50]])
    assert r["volume"] == pytest.approx(math.pi * 25 * 50, rel=0.02)


def test_deform_twist_keeps_volume(cad):
    cad("add_box", at=[0, 0, 0], size=[10, 10, 40], tag="b")
    v0 = cad("measure", kind="volume", select={"tags": ["b"]})["value"]
    cad("deform", select={"tags": ["b"]}, kind="twist", amount=90, refine=4)
    v1 = cad("measure", kind="volume", select={"tags": ["b"]})["value"]
    assert v1 == pytest.approx(v0, rel=0.05)


def test_implicit_sphere(cad):
    r = cad("add_implicit", expr="10 - length(x, y, z)",
            bounds={"min": [-12, -12, -12], "max": [12, 12, 12]},
            edge_length=0.8)
    assert r["volume"] == pytest.approx(4 / 3 * math.pi * 1000, rel=0.03)


def test_implicit_rejects_unsafe(cad):
    with pytest.raises(CadError, match="allowed"):
        cad("add_implicit", expr="__import__('os').getcwd()",
            bounds={"min": [-1, -1, -1], "max": [1, 1, 1]})
    with pytest.raises(CadError, match="unknown name"):
        cad("add_implicit", expr="open - x",
            bounds={"min": [-1, -1, -1], "max": [1, 1, 1]})


def test_smooth_refines(cad):
    cad("add_box", at=[0, 0, 0], size=[10, 10, 10], tag="b")
    r = cad("smooth", select={"tags": ["b"]}, angle=95, refine=2)
    assert r["triangles"] > 12


# ---------------------------------------------------------------- M3 import

def test_dxf_roundtrip(tmp_path):
    cad = Cad(units="mm")
    cad("add_line", start=[0, 0], end=[100, 0])
    cad("add_circle", center=[50, 50], radius=20)
    cad("add_arc", center=[0, 0], radius=30, start_angle=0, end_angle=90)
    cad("add_rect", at=[0, 0], width=40, height=40, layer="frames")
    cad("add_text", at=[10, 80], text="HELLO", height=10)
    dxf = str(tmp_path / "t.dxf")
    cad("export", path=dxf)

    cad2 = Cad(units="mm")
    r = cad2("import_dxf", path=dxf)
    assert r["imported"] == {"LINE": 1, "CIRCLE": 1, "ARC": 1,
                             "POLYLINE": 1, "TEXT": 1}
    assert r["skipped"] == {}
    assert "frames" in cad2("doc_info")["layers"]
    got = cad2("get", id=r["created"][1])["entity"]
    assert got["type"] == "circle" and got["radius"] == pytest.approx(20)


# ---------------------------------------------------------------- M4 midline

def test_fillet_chamfer(cad):
    cad("add_rect", at=[0, 0], width=100, height=100, tag="r")
    r = cad("fillet", select={"tags": ["r"]}, radius=10)
    assert r["corners"] == 4 and r["clamped"] == 0
    a = cad("measure", kind="area", select={"tags": ["r"]})["value"]
    # rounded rect area = full - 4 corners * (r^2 - pi r^2 / 4)
    assert a == pytest.approx(10000 - (4 - math.pi) * 100, rel=0.01)
    cad("add_rect", at=[200, 0], width=100, height=100, tag="c")
    r2 = cad("chamfer", select={"tags": ["c"]}, distance=10)
    assert r2["corners"] == 4
    a2 = cad("measure", kind="area", select={"tags": ["c"]})["value"]
    assert a2 == pytest.approx(10000 - 2 * 100, rel=0.001)


def test_angular_radial_dims(cad):
    cad("add_circle", center=[0, 0], radius=40, tag="c")
    r = cad("add_dim_radial", of={"tags": ["c"]}, direction=30)
    assert r["value"] == pytest.approx(40)
    r2 = cad("add_dim_angular", center=[0, 0], p1=[100, 0], p2=[0, 100])
    assert r2["value"] == pytest.approx(90)
    cad("rotate", select="all", angle=45)  # transforms must not crash
    assert cad("validate")["valid"]


def test_project_elevation(cad):
    cad("add_cylinder", at=[0, 0, 0], radius=10, height=30, segments=64)
    r = cad("project", select={"types": ["solid"]}, axis="y")
    a = cad("measure", kind="area", select=r["created"])["value"]
    assert a == pytest.approx(20 * 30, rel=0.02)


def test_shell(cad):
    cad("add_box", at=[0, 0, 0], size=[60, 40, 30], tag="b")
    cad("shell", select={"tags": ["b"]}, thickness=4)
    v = cad("measure", kind="volume", select={"tags": ["b"]})["value"]
    assert v == pytest.approx(60 * 40 * 30 - 52 * 32 * 22, rel=0.01)


# ---------------------------------------------------------------- V4 parametrics

def test_expressions_in_params(cad):
    cad("set_param", name="r", value=25)
    cad("add_circle", center=["r*2", 0], radius="r")
    ent = cad("get", id="e1")["entity"]
    assert ent["center"] == [50.0, 0.0] and ent["radius"] == 25.0


def test_unknown_param_expression_hints(cad):
    with pytest.raises(CadError, match="unknown name"):
        cad("add_circle", center=[0, 0], radius="bogus*2")


def test_recipe_regenerate(tmp_path):
    cad = Cad(str(tmp_path / "p.json"))
    cad("recipe_set", run=True, commands=[
        {"op": "define_param", "name": "w", "value": 100},
        {"op": "add_rect", "at": [0, 0], "width": "w", "height": "w/2",
         "tag": "r"},
    ])
    a1 = cad("measure", kind="area", select={"tags": ["r"]})["value"]
    assert a1 == pytest.approx(5000)
    cad("regenerate", params={"w": 200})
    a2 = cad("measure", kind="area", select={"tags": ["r"]})["value"]
    assert a2 == pytest.approx(20000)  # everything re-coordinated


def test_recipe_forbids_recursion(cad):
    with pytest.raises(CadError, match="cannot be part"):
        cad("recipe_set", commands=[{"op": "regenerate"}])


def test_levels_in_expressions(cad):
    cad("add_level", name="L2", elevation=3200, height=3000)
    cad("add_box", at=[0, 0, "level('L2')"], size=[100, 100, "level_top('L2')-level('L2')"])
    bb = cad("get", id="e1")["bbox"]
    assert bb["min"][2] == 3200 and bb["max"][2] == pytest.approx(6200)


def test_grid_and_lookup(cad):
    cad("set_param", name="bay", value=4000)
    cad("add_grid", x={"start": 0, "count": 3, "spacing": "bay"},
        y=[0, 5000])
    cad("add_circle", center=["grid_x('C')", "grid_y('2')"], radius=100)
    ent = cad("get", id="e2")["entity"]
    assert ent["center"] == [8000.0, 5000.0]
    cad("move", select="e1", by=[100, 0])  # grids translate fine
    with pytest.raises(CadError, match="translated"):
        cad("rotate", select="e1", angle=45)


# ---------------------------------------------------------------- V4 semantics

def test_room_and_program(cad):
    cad("add_room", name="OFFICE", level="L1",
        points=[[0, 0], [5000, 0], [5000, 4000], [0, 4000]])
    cad("add_room", name="HALL", level="L1",
        points=[[5000, 0], [8000, 0], [8000, 4000], [5000, 4000]])
    rep = cad("program")
    assert rep["total_room_area"] == pytest.approx(32_000_000)
    assert rep["by_name"]["OFFICE"] == pytest.approx(20_000_000)
    assert rep["rooms"][0]["area_m2"] == pytest.approx(20.0)
    assert rep["by_level"]["L1"] == pytest.approx(32_000_000)


def test_roof_gable_volume(cad):
    cad("add_rect", at=[0, 0], width=10000, height=8000, tag="fp")
    r = cad("add_roof", footprint={"tags": ["fp"]}, kind="gable",
            pitch=30, thickness=200, overhang=0)
    expect = 10000 * 8000 * 200 / math.cos(math.radians(30))
    assert r["volume"] == pytest.approx(expect, rel=0.05)


def test_stair_comfort(cad):
    r = cad("add_stair", at=[0, 0], rise=3200)
    assert r["risers"] >= 18 and 150 <= r["riser"] <= 180
    assert 240 <= r["tread"] <= 350
    assert r["volume"] > 0


def test_facade_counts(cad):
    r = cad("add_facade", start=[0, 0], end=[12000, 0], height=6000,
            spacing=2000, tag="f")
    assert r["cols"] == 6 and r["rows"] == 3
    assert len(r["created"]) == 2
    assert cad("measure", kind="volume", select=r["created"])["value"] > 0


def test_surface_flat_volume(cad):
    r = cad("add_surface", expr="100", thickness=50,
            bounds={"min": [0, 0], "max": [1000, 800]}, samples=32)
    assert r["volume"] == pytest.approx(1000 * 800 * 50, rel=0.05)


def test_diff(tmp_path):
    cad = Cad(str(tmp_path / "d.json"))
    cad("set_param", name="bay", value=4000)
    cad("add_rect", at=[0, 0], width="bay", height=1000, tag="r")
    cad.save()
    cad("snapshot", name="a")
    cad("set_param", name="bay", value=5000)
    cad("delete", select={"tags": ["r"]})
    cad("add_rect", at=[0, 0], width="bay", height=1000, tag="r")
    d = cad("diff", against="a")
    assert d["params_changed"]["bay"] == {"from": 4000.0, "to": 5000.0}
    assert d["added"]["count"] == 1 and d["removed"]["count"] == 1
    assert d["metrics"]["area_2d"]["to"] > d["metrics"]["area_2d"]["from"]


# ---------------------------------------------------------------- viewer

def test_viewer_payloads(tmp_path):
    from modulor.exporters.mesh3d import glb_bytes
    from modulor.exporters.svg import svg_string
    from modulor.viewer.server import (DocWatcher, _mesh_payload,
                                         _state_payload)

    p = str(tmp_path / "doc.json")
    cad = Cad(p)
    cad("add_wall", path=[[0, 0], [2000, 0]], thickness=100, tag="w")
    cad("add_box", at=[0, 0, 0], size=[300, 300, 300])
    cad.save()

    watcher = DocWatcher(p)
    doc, mtime = watcher.get()
    assert doc is not None and mtime > 0

    state = _state_payload(doc, mtime, p)
    assert state["exists"] and state["has_2d"] and state["has_3d"]
    assert state["counts"] == {"wall": 1, "solid": 1}

    mesh = _mesh_payload(doc, doc.select("all"))
    assert len(mesh["objects"]) == 2
    o = mesh["objects"][0]
    assert len(o["positions"]) == len(o["normals"]) > 0
    assert len(o["positions"]) % 9 == 0  # whole triangles

    svg, meta = svg_string(doc, doc.select("all"))
    assert svg.startswith("<svg") and meta["primitives"] > 0
    blob, meta3 = glb_bytes(doc, doc.select("all"))
    assert blob[:4] == b"glTF" and meta3["objects"] == 2

    # watcher follows file changes, survives a stale read
    cad("add_circle", center=[0, 0], radius=50)
    cad.save()
    doc2, mtime2 = watcher.get()
    assert mtime2 >= mtime and len(doc2.entities) == 3
