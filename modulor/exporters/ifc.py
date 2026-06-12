"""IFC4 exporter — the bridge from agent-made models into BIM workflows
(Revit, Archicad, Navisworks, model checkers...).

Hand-written STEP/SPF text like every other Modulor exporter: no
dependencies. What makes this exporter special is that it is *semantic*:

  wall  -> IfcWall (extruded footprint) + IfcOpeningElement voids
  level -> IfcBuildingStorey (elements assigned by elevation)
  grid  -> IfcGrid with labeled axes
  room  -> IfcSpace with an area quantity (schedulable)
  solid -> IfcBuildingElementProxy (triangulated, IFC4 tessellation)
  material -> IfcMaterial + surface color

Everything is written in metres (IFC convention), world coordinates,
deterministic GUIDs (same document -> byte-identical file, diff-friendly).
2D drafting entities (lines, dims, text) are out of scope and reported.
"""
from __future__ import annotations

import hashlib
import time

from .. import geometry as g
from .. import shapes
from ..errors import CadError

_GUID_ALPHABET = ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                  "abcdefghijklmnopqrstuvwxyz_$")


def _guid(seed: str) -> str:
    """Deterministic 22-char IFC GlobalId from a seed string."""
    digest = hashlib.md5(seed.encode("utf-8"), usedforsecurity=False).digest()
    n = int.from_bytes(digest[:16], "big")
    n &= (1 << 128) - 1
    out = []
    for _ in range(22):
        out.append(_GUID_ALPHABET[n & 63])
        n >>= 6
    return "".join(reversed(out))


def _num(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    if s in ("", "-0"):
        s = "0"
    if "." not in s and "E" not in s.upper():
        s += "."
    return s


def _str(s: str) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "''") + "'"


class _Spf:
    """Tiny STEP physical-file writer with id allocation."""

    def __init__(self):
        self.lines: list[str] = []
        self._next = 0

    def w(self, typ: str, *args) -> int:
        self._next += 1
        self.lines.append(f"#{self._next}={typ}({','.join(args)});")
        return self._next

    @staticmethod
    def ref(eid: int) -> str:
        return f"#{eid}"

    @staticmethod
    def refs(ids) -> str:
        return "(" + ",".join(f"#{i}" for i in ids) + ")"


def export_ifc(doc, ids, path: str) -> dict:
    s = _Spf()
    R = _Spf.ref
    scale = g.unit_scale(doc.units) / 1000.0  # doc units -> metres
    name = doc.meta.get("name") or "model"

    def gid(key: str) -> str:
        return _str(_guid(f"{name}|{key}"))

    def pt3(x, y, z) -> int:
        return s.w("IFCCARTESIANPOINT",
                   f"({_num(x)},{_num(y)},{_num(z)})")

    def pt2(x, y) -> int:
        return s.w("IFCCARTESIANPOINT", f"({_num(x)},{_num(y)})")

    def placement3d(z: float = 0.0) -> int:
        origin = pt3(0, 0, z)
        return s.w("IFCAXIS2PLACEMENT3D", R(origin), "$", "$")

    # ---------------- header graph
    org = s.w("IFCORGANIZATION", "$", _str("Modulor"), "$", "$", "$")
    person = s.w("IFCPERSON", "$", "$", _str("Modulor"), "$", "$", "$", "$", "$")
    p_and_o = s.w("IFCPERSONANDORGANIZATION", R(person), R(org), "$")
    from .. import __version__
    app = s.w("IFCAPPLICATION", R(org), _str(__version__),
              _str("Modulor"), _str("modulor"))
    history = s.w("IFCOWNERHISTORY", R(p_and_o), R(app), "$", ".ADDED.",
                  "$", "$", "$", str(int(time.time())))

    # units: everything is converted to metres on the way out
    u_len = s.w("IFCSIUNIT", "*", ".LENGTHUNIT.", "$", ".METRE.")
    u_area = s.w("IFCSIUNIT", "*", ".AREAUNIT.", "$", ".SQUARE_METRE.")
    u_vol = s.w("IFCSIUNIT", "*", ".VOLUMEUNIT.", "$", ".CUBIC_METRE.")
    u_ang = s.w("IFCSIUNIT", "*", ".PLANEANGLEUNIT.", "$", ".RADIAN.")
    units = s.w("IFCUNITASSIGNMENT", _Spf.refs([u_len, u_area, u_vol, u_ang]))

    world = placement3d()
    ctx = s.w("IFCGEOMETRICREPRESENTATIONCONTEXT", "$", _str("Model"),
              "3", "1.E-5", R(world), "$")

    project = s.w("IFCPROJECT", gid("project"), R(history), _str(name),
                  "$", "$", "$", "$", _Spf.refs([ctx]), R(units))
    site = s.w("IFCSITE", gid("site"), R(history), _str("Site"), "$", "$",
               R(s.w("IFCLOCALPLACEMENT", "$", R(placement3d()))),
               "$", "$", ".ELEMENT.", "$", "$", "$", "$", "$")
    building = s.w("IFCBUILDING", gid("building"), R(history),
                   _str("Building"), "$", "$",
                   R(s.w("IFCLOCALPLACEMENT", "$", R(placement3d()))),
                   "$", "$", ".ELEMENT.", "$", "$", "$")
    s.w("IFCRELAGGREGATES", gid("rel-proj-site"), R(history), "$", "$",
        R(project), _Spf.refs([site]))
    s.w("IFCRELAGGREGATES", gid("rel-site-bldg"), R(history), "$", "$",
        R(site), _Spf.refs([building]))

    # ---------------- storeys from levels (or a default ground storey)
    levels = sorted(doc.levels.items(), key=lambda kv: kv[1]["elevation"]) \
        or [("Level 0", {"elevation": 0.0})]
    storeys: list[tuple[str, float, int]] = []
    for lname, lv in levels:
        elev = float(lv["elevation"]) * scale
        st = s.w("IFCBUILDINGSTOREY", gid(f"storey-{lname}"), R(history),
                 _str(lname), "$", "$",
                 R(s.w("IFCLOCALPLACEMENT", "$", R(placement3d(elev)))),
                 "$", "$", ".ELEMENT.", _num(elev))
        storeys.append((lname, float(lv["elevation"]), st))
    s.w("IFCRELAGGREGATES", gid("rel-bldg-storeys"), R(history), "$", "$",
        R(building), _Spf.refs([st for _, _, st in storeys]))

    def storey_for(z_doc_units: float) -> tuple[str, float, int]:
        best = storeys[0]
        for entry in storeys:
            if entry[1] <= z_doc_units + 1e-6:
                best = entry
        return best

    # ---------------- materials
    mat_ids: dict[str, int] = {}
    style_ids: dict[str, int] = {}

    def material(mname: str | None):
        mname = mname or "default"
        if mname not in mat_ids:
            mat_ids[mname] = s.w("IFCMATERIAL", _str(mname), "$", "$")
            color = shapes.parse_color(
                doc.materials.get(mname, doc.materials["default"])["color"])
            rgb = s.w("IFCCOLOURRGB", "$", _num(color[0]), _num(color[1]),
                      _num(color[2]))
            shading = s.w("IFCSURFACESTYLESHADING", R(rgb), "0.")
            style_ids[mname] = s.w("IFCSURFACESTYLE", _str(mname), ".BOTH.",
                                   _Spf.refs([shading]))
        return mat_ids[mname], style_ids[mname]

    def style_item(item: int, mname: str | None):
        _, style = material(mname)
        s.w("IFCSTYLEDITEM", R(item), _Spf.refs([style]), "$")

    # ---------------- geometry helpers
    def polyline2d(contour, close: bool = True) -> int:
        pts = [pt2(x * scale, y * scale) for x, y in contour]
        if close:
            pts.append(pts[0])
        return s.w("IFCPOLYLINE", _Spf.refs(pts))

    def profile_from_contours(contours) -> int:
        outer = max(contours, key=lambda c: abs(g.polygon_area(c)))
        holes = [c for c in contours if c is not outer]
        if holes:
            return s.w("IFCARBITRARYPROFILEDEFWITHVOIDS", ".AREA.", "$",
                       R(polyline2d(outer)),
                       _Spf.refs([polyline2d(h) for h in holes]))
        return s.w("IFCARBITRARYCLOSEDPROFILEDEF", ".AREA.", "$",
                   R(polyline2d(outer)))

    z_dir = s.w("IFCDIRECTION", "(0.,0.,1.)")

    def extruded(contours, z0_doc: float, height_doc: float,
                 mname: str | None) -> int:
        profile = profile_from_contours(contours)
        pos = placement3d(z0_doc * scale)
        solid = s.w("IFCEXTRUDEDAREASOLID", R(profile), R(pos), R(z_dir),
                    _num(height_doc * scale))
        style_item(solid, mname)
        return s.w("IFCSHAPEREPRESENTATION", R(ctx), _str("Body"),
                   _str("SweptSolid"), _Spf.refs([solid]))

    def tessellated(ent) -> int:
        mesh = ent["mesh"]
        coords = s.w("IFCCARTESIANPOINTLIST3D", "(" + ",".join(
            f"({_num(v[0] * scale)},{_num(v[1] * scale)},{_num(v[2] * scale)})"
            for v in mesh["vertices"]) + ")", "$")
        idx = "(" + ",".join(
            f"({t[0] + 1},{t[1] + 1},{t[2] + 1})"
            for t in mesh["triangles"]) + ")"
        faceset = s.w("IFCTRIANGULATEDFACESET", R(coords), "$", ".T.",
                      idx, "$")
        style_item(faceset, ent.get("material"))
        return s.w("IFCSHAPEREPRESENTATION", R(ctx), _str("Body"),
                   _str("Tessellation"), _Spf.refs([faceset]))

    def product_shape(rep: int) -> int:
        return s.w("IFCPRODUCTDEFINITIONSHAPE", "$", "$", _Spf.refs([rep]))

    def local_placement(storey_id: int) -> int:
        # geometry is absolute; placements form an identity chain
        return s.w("IFCLOCALPLACEMENT", "$", R(placement3d()))

    # ---------------- entities
    contained: dict[int, list[int]] = {}
    space_aggr: dict[int, list[int]] = {}
    mat_assoc: dict[str, list[int]] = {}
    counts: dict[str, int] = {}
    skipped: dict[str, int] = {}

    def count(k):
        counts[k] = counts.get(k, 0) + 1

    for eid in ids:
        ent = doc.entities[eid]
        t = ent["type"]
        label = _str(ent.get("tag") or eid)

        if t == "wall":
            contours = shapes.wall_footprint(doc, ent,
                                             with_openings=False).to_polygons()
            defaults = shapes.wall_defaults(doc)
            height = float(ent.get("height") or defaults["height"])
            rep = extruded(contours, 0.0, height, ent.get("material"))
            _, _, st = storey_for(0.0)
            wall = s.w("IFCWALL", gid(f"wall-{eid}"), R(history), label,
                       "$", "$", R(local_placement(st)),
                       R(product_shape(rep)), _str(eid), "$")
            contained.setdefault(st, []).append(wall)
            mat_assoc.setdefault(ent.get("material") or "default",
                                 []).append(wall)
            count("IfcWall")

            for k, op in enumerate(ent.get("openings", [])):
                kind = op.get("type", "door")
                if kind == "window":
                    sill = float(op.get("sill", defaults["window_sill"]))
                    head = float(op.get("head", defaults["window_head"]))
                else:
                    sill = float(op.get("sill", 0.0))
                    head = float(op.get("head", defaults["door_head"]))
                head = min(head, height)
                if head <= sill:
                    continue
                cut = shapes._opening_rect_cs(ent, op).to_polygons()
                orep = extruded(cut, sill, head - sill, None)
                opening = s.w("IFCOPENINGELEMENT",
                              gid(f"open-{eid}-{k}"), R(history),
                              _str(f"{kind} {k + 1}"), "$", "$",
                              R(local_placement(st)),
                              R(product_shape(orep)), "$", ".OPENING.")
                s.w("IFCRELVOIDSELEMENT", gid(f"void-{eid}-{k}"),
                    R(history), "$", "$", R(wall), R(opening))
                count("IfcOpeningElement")

        elif t == "solid":
            box = shapes.entity_bbox(doc, eid)
            zmin = float(box.min[2]) if not box.empty else 0.0
            _, _, st = storey_for(zmin)
            rep = tessellated(ent)
            proxy = s.w("IFCBUILDINGELEMENTPROXY",
                        gid(f"solid-{eid}"), R(history), label, "$", "$",
                        R(local_placement(st)), R(product_shape(rep)),
                        _str(eid), "$")
            contained.setdefault(st, []).append(proxy)
            mat_assoc.setdefault(ent.get("material") or "default",
                                 []).append(proxy)
            count("IfcBuildingElementProxy")

        elif t == "room":
            lvl = ent.get("level")
            entry = next((e for e in storeys if e[0] == lvl), None) \
                or storey_for(0.0)
            lname, elev_doc, st = entry
            height = float(doc.levels.get(lname, {}).get("height") or
                           3000.0 / g.unit_scale(doc.units))
            rep = extruded([g.ensure_ccw(ent["points"])], elev_doc, height,
                           None)
            space = s.w("IFCSPACE", gid(f"room-{eid}"), R(history),
                        _str(ent["name"]), "$", "$",
                        R(local_placement(st)), R(product_shape(rep)),
                        _str(eid), ".ELEMENT.", ".INTERNAL.", "$")
            space_aggr.setdefault(st, []).append(space)
            area_m2 = abs(g.polygon_area(ent["points"])) * scale * scale
            qty = s.w("IFCQUANTITYAREA", _str("NetFloorArea"), "$", "$",
                      _num(area_m2), "$")
            eq = s.w("IFCELEMENTQUANTITY", gid(f"q-{eid}"), R(history),
                     _str("Qto_SpaceBaseQuantities"), "$", "$",
                     _Spf.refs([qty]))
            s.w("IFCRELDEFINESBYPROPERTIES", gid(f"rq-{eid}"), R(history),
                "$", "$", _Spf.refs([space]), R(eq))
            count("IfcSpace")

        elif t == "grid":
            u_axes, v_axes = [], []
            ys0, ys1 = ent["ys"][0], ent["ys"][-1]
            xs0, xs1 = ent["xs"][0], ent["xs"][-1]
            ext = max(xs1 - xs0, ys1 - ys0) * 0.05
            for x, lab in zip(ent["xs"], ent["x_labels"]):
                curve = s.w("IFCPOLYLINE", _Spf.refs([
                    pt2(x * scale, (ys0 - ext) * scale),
                    pt2(x * scale, (ys1 + ext) * scale)]))
                u_axes.append(s.w("IFCGRIDAXIS", _str(lab), R(curve), ".T."))
            for y, lab in zip(ent["ys"], ent["y_labels"]):
                curve = s.w("IFCPOLYLINE", _Spf.refs([
                    pt2((xs0 - ext) * scale, y * scale),
                    pt2((xs1 + ext) * scale, y * scale)]))
                v_axes.append(s.w("IFCGRIDAXIS", _str(lab), R(curve), ".T."))
            _, _, st = storey_for(0.0)
            grid = s.w("IFCGRID", gid(f"grid-{eid}"), R(history), label,
                       "$", "$", R(local_placement(st)), "$",
                       _Spf.refs(u_axes), _Spf.refs(v_axes), "$", "$")
            contained.setdefault(st, []).append(grid)
            count("IfcGrid")

        else:
            skipped[t] = skipped.get(t, 0) + 1

    if not counts:
        raise CadError("empty_selection",
                       "nothing in the selection maps to IFC",
                       hint="IFC export covers walls, solids, rooms, grids, "
                            "levels and materials")

    # ---------------- relationships
    for st, elems in contained.items():
        s.w("IFCRELCONTAINEDINSPATIALSTRUCTURE", gid(f"cont-{st}"),
            R(history), "$", "$", _Spf.refs(elems), R(st))
    for st, spaces in space_aggr.items():
        s.w("IFCRELAGGREGATES", gid(f"aggr-{st}"), R(history), "$", "$",
            R(st), _Spf.refs(spaces))
    for mname, elems in mat_assoc.items():
        mid, _ = material(mname)
        s.w("IFCRELASSOCIATESMATERIAL", gid(f"mat-{mname}"), R(history),
            "$", "$", _Spf.refs(elems), R(mid))

    # ---------------- file assembly
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    header = "\n".join([
        "ISO-10303-21;",
        "HEADER;",
        "FILE_DESCRIPTION(('ViewDefinition [ReferenceView]'),'2;1');",
        f"FILE_NAME({_str(name + '.ifc')},{_str(stamp)},({_str('Modulor')}),"
        f"({_str('Modulor')}),{_str('Modulor ' + __version__)},"
        f"{_str('Modulor')},'');",
        "FILE_SCHEMA(('IFC4'));",
        "ENDSEC;",
        "DATA;",
    ])
    body = "\n".join(s.lines)
    footer = "ENDSEC;\nEND-ISO-10303-21;\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + "\n" + body + "\n" + footer)

    out = {"path": path, "schema": "IFC4",
           "storeys": len(storeys), "exported": counts}
    if skipped:
        out["skipped"] = skipped
        out["note"] = ("2D drafting entities are not part of IFC export; "
                       "use .dxf/.svg for drawings")
    return out
