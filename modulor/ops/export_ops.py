"""Export and render ops. Format is inferred from the file extension."""
from __future__ import annotations

import json
import os

from ..errors import CadError
from . import P, op

FORMATS = (".svg", ".dxf", ".png", ".obj", ".stl", ".glb", ".json")


@op("export",
    doc="Export to a file; format from the extension. 2D formats: .svg .dxf "
        "(drawings, dims, walls in plan). 3D formats: .obj .stl .glb "
        "(solids + walls as meshes). .png renders an image, .json saves a "
        "document copy.",
    params={
        "path": P.string(req=True, doc=f"output file, one of {FORMATS}"),
        "select": P.select(default="all"),
        "width": P.integer(default=1200, doc="png only"),
        "height": P.integer(default=900, doc="png only"),
        "camera": P.obj(doc='png only: named view ("iso", "top", "front", ...) '
                            'or {"eye": [x,y,z], "target": [x,y,z], "fov": 45}'),
    },
    example={"op": "export", "path": "out/plan.dxf"},
    returns="format-specific summary, always includes {path}",
    effects="files")
def export(doc, p):
    path = p["path"]
    ext = os.path.splitext(path)[1].lower()
    ids = doc.select(p["select"])
    if not ids:
        raise CadError("empty_selection", "nothing to export")
    _ensure_dir(path)
    if ext == ".svg":
        from ..exporters.svg import export_svg
        return export_svg(doc, ids, path)
    if ext == ".dxf":
        from ..exporters.dxf import export_dxf
        return export_dxf(doc, ids, path)
    if ext == ".obj":
        from ..exporters.mesh3d import export_obj
        return _need_solids(export_obj(doc, ids, path))
    if ext == ".stl":
        from ..exporters.mesh3d import export_stl
        return _need_solids(export_stl(doc, ids, path))
    if ext == ".glb":
        from ..exporters.mesh3d import export_glb
        return _need_solids(export_glb(doc, ids, path))
    if ext == ".png":
        return _render(doc, p, ids, "auto")
    if ext == ".json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc.to_dict(), f, ensure_ascii=False)
        return {"path": path, "entities": len(doc.entities)}
    raise CadError("bad_format", f"unsupported extension {ext!r}",
                   hint=f"supported: {FORMATS}")


@op("import_dxf",
    doc="Import entities from a DXF file (ASCII, R12 through current). "
        "Supported: LINE, CIRCLE, ARC, LWPOLYLINE/POLYLINE (with arc "
        "bulges), TEXT, MTEXT, SPLINE, ELLIPSE — plus layers with colors. "
        "Unsupported entity types are counted in 'skipped', never silently "
        "dropped. This is how you take over an existing human drawing.",
    params={
        "path": P.string(req=True, doc="input .dxf file"),
        "scale": P.number(default=1.0,
                          doc="multiply all coordinates (unit conversion)"),
        "layer_prefix": P.string(default="",
                                 doc="prefix imported layer names, e.g. 'dxf/'"),
    },
    example={"op": "import_dxf", "path": "site_plan.dxf"},
    returns="{created: [ids], imported: {TYPE: n}, skipped: {TYPE: n}, "
            "layers, dxf_units?, warnings?}")
def import_dxf_op(doc, p):
    import os
    if not os.path.exists(p["path"]):
        raise CadError("file_not_found", f"no such file: {p['path']}")
    if p["scale"] <= 0:
        raise CadError("bad_param", "scale must be positive")
    from ..importers.dxf import import_dxf
    return import_dxf(doc, p["path"], p["scale"], p["layer_prefix"])


@op("render",
    doc="Render a PNG image of the model so it can be inspected visually. "
        "mode 'plan' draws the 2D drawing; 'shaded' draws solids/walls in "
        "3D; 'auto' picks shaded when solids exist.",
    params={
        "path": P.string(req=True, doc="output .png file"),
        "mode": P.enum(["auto", "plan", "shaded"], default="auto",
               doc="2D drawing or 3D view; auto picks by content"),
        "select": P.select(default="all"),
        "width": P.integer(default=1200, doc="image width, px"),
        "height": P.integer(default=900, doc="image height, px"),
        "camera": P.obj(doc='shaded only: named view ("iso", "iso_left", '
                            '"top", "front", "right", ...) or '
                            '{"eye": [x,y,z], "target": [x,y,z], "fov": 45}'),
        "labels": P.boolean(default=False,
                            doc="overlay entity ids/tags on the image so you "
                                "can map what you see back to entities"),
    },
    example={"op": "render", "path": "out/iso.png", "mode": "shaded",
             "camera": "iso"},
    returns="{path, width, height, ...}", effects="files")
def render(doc, p):
    ids = doc.select(p["select"])
    if not ids:
        raise CadError("empty_selection", "nothing to render")
    _ensure_dir(p["path"])
    return _render(doc, p, ids, p["mode"])


def _render(doc, p, ids, mode: str):
    types = {doc.entities[eid]["type"] for eid in ids}
    has_3d = bool(types & {"solid", "wall"})
    if mode == "auto":
        # any solid -> shaded; walls without flat 2D entities -> shaded;
        # otherwise a drawing -> plan
        if "solid" in types or types == {"wall"}:
            mode = "shaded"
        else:
            mode = "plan"
    labels = bool(p.get("labels"))
    if mode == "shaded":
        if not has_3d:
            raise CadError("empty_selection",
                           "no solids or walls for a shaded render",
                           hint="use mode='plan' for 2D drawings")
        from ..render.render3d import render_3d
        return render_3d(doc, ids, p["path"], p["width"], p["height"],
                         p.get("camera"), labels=labels)
    from ..render.render2d import render_2d
    return render_2d(doc, ids, p["path"], p["width"], p["height"],
                     labels=labels)


def _need_solids(result: dict) -> dict:
    if result.get("triangles", 0) == 0 and result.get("objects", 1) == 0:
        raise CadError("empty_selection",
                       "selection has no solids or walls to export",
                       hint="3D formats need solid or wall entities")
    return result


def _ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
