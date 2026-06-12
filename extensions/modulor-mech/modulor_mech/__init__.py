"""modulor-mech — mechanical ops for Modulor, and the official template
for building extensions.

What makes this a template worth copying:
- one entry point (`mech = "modulor_mech"` in pyproject) + one
  ``register(api)`` function = the whole integration;
- ops are namespaced automatically (``mech.gear``) — the namespace comes
  from the entry-point name and cannot be escaped;
- the test suite asserts ``check_laws("mech")`` is clean, so the
  extension obeys the same API laws as core.
"""
from __future__ import annotations

import math

__version__ = "0.1.0"


def _involute_gear(module: float, teeth: int, pressure_deg: float,
                   flank_steps: int = 8) -> list[list[float]]:
    """Outline of an involute spur gear centered at the origin."""
    z = teeth
    m = module
    alpha = math.radians(pressure_deg)
    r_pitch = m * z / 2.0
    r_base = r_pitch * math.cos(alpha)
    r_tip = r_pitch + m              # addendum = m
    r_root = max(r_pitch - 1.25 * m, 0.2 * m)  # dedendum = 1.25 m

    def inv(a: float) -> float:      # involute function
        return math.tan(a) - a

    def flank_point(r: float) -> tuple[float, float]:
        """(radius, polar half-angle of the right flank) at radius r."""
        a_r = math.acos(min(r_base / r, 1.0))
        theta = math.pi / (2 * z) + inv(alpha) - inv(a_r)
        return r, theta

    r_start = max(r_root, r_base)
    pts: list[list[float]] = []
    pitch_ang = 2 * math.pi / z
    for k in range(z):
        c = k * pitch_ang

        def add(r, ang):
            pts.append([r * math.cos(c + ang), r * math.sin(c + ang)])

        # root arc up to the right flank
        _, th_start = flank_point(r_start)
        if r_root < r_start - 1e-12:
            add(r_root, -pitch_ang / 2 + 0.04 * pitch_ang)
            add(r_root, -th_start - 0.02 * pitch_ang)
        # right flank: root/base -> tip (CCW boundary runs angle - -> +)
        for i in range(flank_steps + 1):
            r = r_start + (r_tip - r_start) * i / flank_steps
            rr, th = flank_point(r)
            add(rr, -th)
        # tip arc
        _, th_tip = flank_point(r_tip)
        add(r_tip, th_tip)
        # left flank: tip -> root (mirror)
        for i in range(flank_steps, -1, -1):
            r = r_start + (r_tip - r_start) * i / flank_steps
            rr, th = flank_point(r)
            if i < flank_steps:  # tip point already added
                add(rr, th)
        if r_root < r_start - 1e-12:
            add(r_root, th_start + 0.02 * pitch_ang)
    return pts


def register(api):
    P = api.P

    @api.op(
        "gear",
        doc="Add an involute spur gear outline (a region; extrude it for a "
            "solid). Standard full-depth teeth: addendum = module, "
            "dedendum = 1.25 x module.",
        params={
            "module": P.number(req=True, doc="gear module (tooth size), > 0"),
            "teeth": P.integer(req=True, doc="number of teeth (6..200)"),
            "at": P.point2(default=[0.0, 0.0], doc="gear center"),
            "bore": P.number(default=0.0, doc="center hole diameter (0 = none)"),
            "pressure_angle": P.number(default=20.0,
                                       doc="pressure angle, degrees (14.5-25)"),
            "layer": P.layer(),
            "tag": P.tag(),
        },
        example={"op": "mech.gear", "module": 2, "teeth": 24, "bore": 8},
        returns="{created: [id], pitch_diameter, tip_diameter, root_diameter}")
    def gear(doc, p):
        from modulor import geometry as g
        from modulor.errors import CadError

        m, z = p["module"], p["teeth"]
        if m <= 0:
            raise CadError("bad_param", "module must be > 0")
        if not 6 <= z <= 200:
            raise CadError("bad_param", "teeth must be between 6 and 200")
        if not 14.5 <= p["pressure_angle"] <= 25:
            raise CadError("bad_param", "pressure_angle must be 14.5..25")
        r_pitch = m * z / 2.0
        if p["bore"] < 0 or (p["bore"] and p["bore"] / 2 >= r_pitch - 1.5 * m):
            raise CadError("bad_param",
                           "bore must be smaller than the root circle")

        cx, cy = p["at"]
        outline = [[x + cx, y + cy]
                   for x, y in _involute_gear(m, z, p["pressure_angle"])]
        contours = [g.ensure_ccw(outline)]
        if p["bore"]:
            hole = g.circle_points([cx, cy], p["bore"] / 2.0)
            contours.append(g.ensure_ccw(hole)[::-1])  # hole winds CW
        eid = doc.add_entity("region", {"contours": contours},
                             layer=p["layer"] or "mech", tag=p["tag"])
        return {"created": [eid],
                "pitch_diameter": round(2 * r_pitch, 6),
                "tip_diameter": round(2 * (r_pitch + m), 6),
                "root_diameter": round(2 * (r_pitch - 1.25 * m), 6)}
