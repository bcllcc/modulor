"""modulor-mech extension tests — including the law compliance check
every Modulor extension is expected to run."""
import math

import pytest

from modulor import Cad, CadError
from modulor.plugins import check_laws, load_plugins, plugin_status

load_plugins()


def test_plugin_loaded_clean():
    status = plugin_status()
    assert "mech" in status["loaded"]
    assert not status["errors"]


def test_obeys_the_api_laws():
    assert check_laws("mech") == []


def test_gear_geometry():
    cad = Cad(units="mm")
    r = cad("mech.gear", module=2, teeth=24, bore=8, tag="g1")
    assert r["pitch_diameter"] == pytest.approx(48.0)
    assert r["tip_diameter"] == pytest.approx(52.0)
    assert r["root_diameter"] == pytest.approx(43.0)

    area = cad("measure", kind="area", select={"tags": ["g1"]})["value"]
    r_tip, r_root = 26.0, 21.5
    assert math.pi * r_root**2 * 0.9 < area + math.pi * 16 < math.pi * r_tip**2
    bb = cad("measure", kind="bbox", select={"tags": ["g1"]})
    assert bb["size"][0] == pytest.approx(52.0, rel=0.01)


def test_gear_is_a_normal_entity():
    """The output is an ordinary region: extrudable, transformable,
    exportable — extensions add ops, never special entity types."""
    cad = Cad(units="mm")
    cad("mech.gear", module=2, teeth=12, tag="g")
    out = cad("extrude", select={"tags": ["g"]}, height=8, tag="solid")
    assert out["volume"] > 0
    cad("rotate", select={"tags": ["g"]}, angle=7.5)  # half a tooth pitch
    assert cad("validate")["valid"]


def test_gear_rejects_bad_input():
    cad = Cad(units="mm")
    with pytest.raises(CadError):
        cad("mech.gear", module=-1, teeth=24)
    with pytest.raises(CadError):
        cad("mech.gear", module=2, teeth=3)
    with pytest.raises(CadError):
        cad("mech.gear", module=2, teeth=24, bore=100)


def test_discoverable_like_core_ops():
    cad = Cad(units="mm")
    info = cad("help", name="mech.gear")
    assert info["origin"] == "mech"
    assert "module" in info["params"]
