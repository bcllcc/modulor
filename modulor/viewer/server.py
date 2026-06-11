"""`modulor serve` — a read-only browser window onto a document file.

The point: agents keep working through their own channels (CLI / REPL /
MCP / Python); this server just watches the .json document and the browser
follows along live. Strictly an observer — no editing endpoints exist.

stdlib only: http.server + the existing exporters. The frontend is one
embedded HTML file (no build step, no CDN, works offline).

Routes:
  GET /                     viewer page
  GET /api/state            doc summary + mtime fingerprint (clients poll this)
  GET /api/svg?layers=a,b   2D drawing as SVG
  GET /api/mesh?layers=a,b  3D geometry as flat-shaded JSON buffers
  GET /api/download/EXT     svg | dxf | glb | stl | json  (attachment)
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

from .. import shapes
from ..document import Document
from ..errors import CadError
from ..render.render3d import _feature_edges

_HTML_PATH = os.path.join(os.path.dirname(__file__), "index.html")


class DocWatcher:
    """Reload the document from disk whenever its mtime changes."""

    def __init__(self, path: str):
        self.path = path
        self._doc: Document | None = None
        self._mtime: float = -1.0
        self._lock = threading.Lock()

    def get(self) -> tuple[Document | None, float]:
        with self._lock:
            try:
                mtime = os.path.getmtime(self.path)
            except OSError:
                self._doc, self._mtime = None, -1.0
                return None, -1.0
            if mtime != self._mtime:
                try:
                    self._doc = Document.load(self.path)
                    self._mtime = mtime
                except (json.JSONDecodeError, CadError, OSError):
                    # mid-write or malformed: keep serving the previous state
                    pass
            return self._doc, self._mtime


def _state_payload(doc: Document | None, mtime: float, path: str) -> dict:
    if doc is None:
        return {"exists": False, "doc": path, "mtime": mtime,
                "hint": "waiting for the document file to be created"}
    counts: dict[str, int] = {}
    for ent in doc.entities.values():
        counts[ent["type"]] = counts.get(ent["type"], 0) + 1
    box = shapes.doc_bbox(doc)
    return {
        "exists": True,
        "doc": path,
        "mtime": mtime,
        "name": doc.meta.get("name"),
        "units": doc.units,
        "layers": {k: {"color": v.get("color", "#222"),
                       "visible": v.get("visible", True)}
                   for k, v in doc.layers.items()},
        "counts": counts,
        "entities": len(doc.entities),
        "bbox": box.as_dict(),
        "has_2d": any(e["type"] != "solid" for e in doc.entities.values()),
        "has_3d": any(e["type"] in ("solid", "wall")
                      for e in doc.entities.values()),
    }


def _mesh_payload(doc: Document, ids) -> dict:
    """Flat-shaded buffers: vertices duplicated per triangle so each face
    carries its own normal (matches the PNG renderer's look)."""
    objects = []
    box = shapes.doc_bbox(doc, ids)
    for m in shapes.collect_meshes(doc, ids):
        v = m["verts"]
        t = m["tris"]
        tri_pts = v[t]                                   # (n, 3, 3)
        e1 = tri_pts[:, 1] - tri_pts[:, 0]
        e2 = tri_pts[:, 2] - tri_pts[:, 0]
        n = np.cross(e1, e2)
        lens = np.linalg.norm(n, axis=1, keepdims=True)
        n = np.divide(n, lens, out=np.zeros_like(n), where=lens > 1e-12)
        flat_pos = tri_pts.reshape(-1, 3)
        flat_nrm = np.repeat(n, 3, axis=0)
        edges = _feature_edges(v, t, n)
        edge_pos = np.array([[v[a], v[b]] for a, b in edges],
                            dtype=float).reshape(-1, 3) if edges else \
            np.zeros((0, 3))
        objects.append({
            "name": m["name"],
            "color": [round(c, 4) for c in m["color"]],
            "positions": np.round(flat_pos, 4).ravel().tolist(),
            "normals": np.round(flat_nrm, 4).ravel().tolist(),
            "edges": np.round(edge_pos, 4).ravel().tolist(),
        })
    return {"objects": objects,
            "bbox": box.as_dict() if not box.empty else None}


def make_handler(watcher: DocWatcher):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep stdout clean for the CLI
            pass

        def do_GET(self):
            try:
                self._route()
            except BrokenPipeError:
                pass
            except Exception as e:
                self._json({"error": f"{type(e).__name__}: {e}"}, status=500)

        # ----------------------------------------------------- routing

        def _route(self):
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            route = url.path

            if route == "/":
                with open(_HTML_PATH, "rb") as f:
                    body = f.read()
                self._raw(body, "text/html; charset=utf-8")
                return

            doc, mtime = watcher.get()

            if route == "/api/state":
                self._json(_state_payload(doc, mtime, watcher.path))
                return
            if doc is None:
                self._json({"error": "document does not exist yet"}, status=404)
                return

            ids = self._select_ids(doc, q)

            if route == "/api/svg":
                from ..exporters.svg import svg_string
                svg, _ = svg_string(doc, ids)
                self._raw(svg.encode("utf-8"), "image/svg+xml")
            elif route == "/api/mesh":
                self._json(_mesh_payload(doc, ids))
            elif route.startswith("/api/download/"):
                self._download(doc, ids, route.rsplit("/", 1)[1])
            else:
                self._json({"error": "not found"}, status=404)

        @staticmethod
        def _select_ids(doc, q):
            layers = q.get("layers", [None])[0]
            if layers:
                wanted = [s for s in layers.split(",") if s]
                return doc.select({"layers": wanted})
            return doc.select("all")

        # ----------------------------------------------------- downloads

        def _download(self, doc, ids, ext):
            name = (doc.meta.get("name") or "model") + "." + ext
            if ext == "svg":
                from ..exporters.svg import svg_string
                data = svg_string(doc, ids)[0].encode("utf-8")
                mime = "image/svg+xml"
            elif ext == "glb":
                from ..exporters.mesh3d import glb_bytes
                data = glb_bytes(doc, ids)[0]
                mime = "model/gltf-binary"
            elif ext == "json":
                data = json.dumps(doc.to_dict(), ensure_ascii=False).encode("utf-8")
                mime = "application/json"
            elif ext in ("dxf", "stl"):
                data = self._via_tempfile(doc, ids, ext)
                mime = "application/octet-stream"
            else:
                self._json({"error": f"unknown format {ext!r}"}, status=404)
                return
            self._raw(data, mime,
                      extra={"Content-Disposition":
                             f'attachment; filename="{name}"'})

        @staticmethod
        def _via_tempfile(doc, ids, ext) -> bytes:
            fd, tmp = tempfile.mkstemp(suffix="." + ext)
            os.close(fd)
            try:
                if ext == "dxf":
                    from ..exporters.dxf import export_dxf
                    export_dxf(doc, ids, tmp)
                else:
                    from ..exporters.mesh3d import export_stl
                    export_stl(doc, ids, tmp)
                with open(tmp, "rb") as f:
                    return f.read()
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

        # ----------------------------------------------------- responses

        def _raw(self, body: bytes, mime: str, status: int = 200, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200):
            self._raw(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                      "application/json; charset=utf-8", status)

    return Handler


def serve(doc_path: str, host: str = "127.0.0.1", port: int = 8400,
          open_browser: bool = True) -> None:
    watcher = DocWatcher(doc_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(watcher))
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(json.dumps({"ok": True, "serving": doc_path, "url": url,
                      "note": "read-only viewer; agents edit via CLI/MCP "
                              "and the page follows live"}),
          flush=True)
    if open_browser:
        import webbrowser
        threading.Thread(target=webbrowser.open, args=(url,),
                         daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
