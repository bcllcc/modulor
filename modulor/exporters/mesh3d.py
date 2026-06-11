"""3D mesh exporters: OBJ (+MTL), binary STL, and GLB (binary glTF 2.0).

OBJ/STL stay in document units, Z-up. GLB follows the glTF convention:
meters, Y-up (we rotate -90 deg about X and scale on the way out).
"""
from __future__ import annotations

import json
import os
import struct

import numpy as np

from .. import geometry as g
from .. import shapes


# ---------------------------------------------------------------- OBJ

def export_obj(doc, ids, path: str) -> dict:
    meshes = shapes.collect_meshes(doc, ids)
    mtl_path = os.path.splitext(path)[0] + ".mtl"
    mats: dict[str, tuple] = {}
    out = [f"# modulor OBJ ({doc.units}, Z-up)",
           f"mtllib {os.path.basename(mtl_path)}"]
    voffset = 1
    for m in meshes:
        mats.setdefault(m["material"], m["color"])
        out.append(f"o {m['name']}")
        out.append(f"usemtl {m['material']}")
        for v in m["verts"]:
            out.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
        for t in m["tris"]:
            out.append(f"f {t[0] + voffset} {t[1] + voffset} {t[2] + voffset}")
        voffset += len(m["verts"])
    with open(path, "w", encoding="ascii") as f:
        f.write("\n".join(out) + "\n")
    mtl = []
    for name, color in mats.items():
        mtl.append(f"newmtl {name}")
        mtl.append(f"Kd {color[0]:.4f} {color[1]:.4f} {color[2]:.4f}")
    with open(mtl_path, "w", encoding="ascii") as f:
        f.write("\n".join(mtl) + "\n")
    return {"path": path, "mtl": mtl_path, "objects": len(meshes),
            "triangles": int(sum(len(m["tris"]) for m in meshes))}


# ---------------------------------------------------------------- STL

def export_stl(doc, ids, path: str) -> dict:
    meshes = shapes.collect_meshes(doc, ids)
    tris = []
    for m in meshes:
        tris.append(m["verts"][m["tris"]])  # (n, 3, 3)
    if tris:
        all_tris = np.concatenate(tris, axis=0)
    else:
        all_tris = np.zeros((0, 3, 3))
    n = len(all_tris)
    e1 = all_tris[:, 1] - all_tris[:, 0]
    e2 = all_tris[:, 2] - all_tris[:, 0]
    normals = np.cross(e1, e2)
    lens = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, lens, out=np.zeros_like(normals),
                        where=lens > 1e-12)
    with open(path, "wb") as f:
        f.write(b"modulor binary STL".ljust(80, b" "))
        f.write(struct.pack("<I", n))
        rec = np.zeros(n, dtype=[("n", "<f4", (3,)), ("v", "<f4", (3, 3)),
                                 ("attr", "<u2")])
        rec["n"] = normals.astype(np.float32)
        rec["v"] = all_tris.astype(np.float32)
        f.write(rec.tobytes())
    return {"path": path, "triangles": int(n)}


# ---------------------------------------------------------------- GLB

def export_glb(doc, ids, path: str) -> dict:
    blob, meta = glb_bytes(doc, ids)
    with open(path, "wb") as f:
        f.write(blob)
    return {"path": path, **meta}


def glb_bytes(doc, ids) -> tuple[bytes, dict]:
    meshes = shapes.collect_meshes(doc, ids)
    scale = g.unit_scale(doc.units) / 1000.0  # doc units -> meters

    bin_parts: list[bytes] = []
    buffer_views = []
    accessors = []
    gltf_meshes = []
    nodes = []
    materials = []
    mat_index: dict[str, int] = {}
    offset = 0

    def add_view(data: bytes, target: int) -> int:
        nonlocal offset
        pad = (-len(data)) % 4
        bin_parts.append(data + b"\x00" * pad)
        buffer_views.append({"buffer": 0, "byteOffset": offset,
                             "byteLength": len(data), "target": target})
        offset += len(data) + pad
        return len(buffer_views) - 1

    for m in meshes:
        # Z-up (CAD) -> Y-up (glTF): (x, y, z) -> (x, z, -y), then to meters
        v = m["verts"].astype(np.float64)
        v = np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1) * scale
        v = v.astype(np.float32)
        idx = m["tris"].astype(np.uint32).ravel()

        vview = add_view(v.tobytes(), 34962)
        iview = add_view(idx.tobytes(), 34963)
        accessors.append({"bufferView": vview, "componentType": 5126,
                          "count": len(v), "type": "VEC3",
                          "min": [float(x) for x in v.min(axis=0)],
                          "max": [float(x) for x in v.max(axis=0)]})
        va = len(accessors) - 1
        accessors.append({"bufferView": iview, "componentType": 5125,
                          "count": len(idx), "type": "SCALAR"})
        ia = len(accessors) - 1

        mname = m["material"]
        if mname not in mat_index:
            mat = doc.materials.get(mname, doc.materials["default"])
            materials.append({
                "name": mname,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [*shapes.parse_color(mat["color"]), 1.0],
                    "metallicFactor": float(mat.get("metallic", 0.0)),
                    "roughnessFactor": float(mat.get("roughness", 0.8)),
                },
            })
            mat_index[mname] = len(materials) - 1

        gltf_meshes.append({"name": m["name"], "primitives": [
            {"attributes": {"POSITION": va}, "indices": ia,
             "material": mat_index[mname]}]})
        nodes.append({"mesh": len(gltf_meshes) - 1, "name": m["name"]})

    bin_blob = b"".join(bin_parts)
    gltf = {
        "asset": {"version": "2.0", "generator": "modulor"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": gltf_meshes,
        "materials": materials,
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    json_blob = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_blob += b" " * ((-len(json_blob)) % 4)

    total = 12 + 8 + len(json_blob) + 8 + len(bin_blob)
    blob = b"".join([
        struct.pack("<III", 0x46546C67, 2, total),       # glTF magic
        struct.pack("<II", len(json_blob), 0x4E4F534A),  # JSON chunk
        json_blob,
        struct.pack("<II", len(bin_blob), 0x004E4942),   # BIN chunk
        bin_blob,
    ])
    return blob, {"objects": len(meshes),
                  "triangles": int(sum(len(m["tris"]) for m in meshes)),
                  "size_bytes": total}
