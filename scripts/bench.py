"""Scale benchmark: a building-sized document, timed end to end.

Run:  python scripts/bench.py
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modulor import Cad  # noqa: E402


def main():
    t_all = time.perf_counter()
    path = os.path.join(tempfile.gettempdir(), "ncad_bench.json")
    cad = Cad(path, units="mm")

    # ---- a 20-story slab tower: 420 walls with openings + 200 columns
    t0 = time.perf_counter()
    commands = [{"op": "doc_new", "units": "mm", "name": "bench"}]
    for floor in range(20):
        z = floor * 3200
        commands.append({"op": "add_wall",
                         "path": [[0, 0], [40000, 0], [40000, 16000],
                                  [0, 16000], [0, 0]],
                         "thickness": 250, "height": 3000, "tag": f"f{floor}"})
        for k in range(10):
            commands.append({"op": "add_wall",
                             "path": [[4000 * (k + 1), 0], [4000 * (k + 1), 16000]],
                             "thickness": 120, "height": 3000})
        for k in range(8):
            commands.append({"op": "add_opening", "wall": {"tags": [f"f{floor}"]},
                             "along": 2500 + 4500 * k, "width": 1800,
                             "type": "window"})
        commands.append({"op": "add_box", "at": [0, 0, z - 200],
                         "size": [40000, 16000, 200]})
    n_cmd = len(commands)
    res = cad.run(commands)
    t_build = time.perf_counter() - t0

    t0 = time.perf_counter()
    cad.save()
    t_save = time.perf_counter() - t0
    size_mb = os.path.getsize(path) / 1e6

    t0 = time.perf_counter()
    r = cad("measure", kind="volume", select="all")
    t_measure = time.perf_counter() - t0

    t0 = time.perf_counter()
    png = os.path.join(tempfile.gettempdir(), "ncad_bench.png")
    cad("render", path=png, mode="shaded", camera="iso",
        width=1200, height=900)
    t_render = time.perf_counter() - t0

    t0 = time.perf_counter()
    glb = os.path.join(tempfile.gettempdir(), "ncad_bench.glb")
    out = cad("export", path=glb)
    t_glb = time.perf_counter() - t0

    print(json.dumps({
        "commands": n_cmd,
        "entities": len(cad.doc.entities),
        "build_s": round(t_build, 2),
        "save_s": round(t_save, 2),
        "doc_mb": round(size_mb, 2),
        "measure_s": round(t_measure, 2),
        "render_s": round(t_render, 2),
        "glb_s": round(t_glb, 2),
        "glb_triangles": out["triangles"],
        "total_s": round(time.perf_counter() - t_all, 2),
    }, indent=1))


if __name__ == "__main__":
    main()
