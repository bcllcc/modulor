"""Tiny software rasterizer + PNG writer. numpy only — no Pillow, no GPU.

Pixel coordinates: x right, y DOWN (image convention). Callers flip CAD y.
"""
from __future__ import annotations

import struct
import zlib

import numpy as np


class Canvas:
    def __init__(self, width: int, height: int, bg=(1.0, 1.0, 1.0)):
        self.w = int(width)
        self.h = int(height)
        self.buf = np.empty((self.h, self.w, 3), dtype=np.float32)
        self.buf[:] = bg

    # ------------------------------------------------------------ lines

    def line(self, p0, p1, color, width: float = 1.0):
        """Draw a segment as a capsule (distance-field fill on a local window)."""
        x0, y0 = float(p0[0]), float(p0[1])
        x1, y1 = float(p1[0]), float(p1[1])
        r = max(width, 1.0) / 2.0
        xmin = max(int(np.floor(min(x0, x1) - r - 1)), 0)
        xmax = min(int(np.ceil(max(x0, x1) + r + 1)), self.w - 1)
        ymin = max(int(np.floor(min(y0, y1) - r - 1)), 0)
        ymax = min(int(np.ceil(max(y0, y1) + r + 1)), self.h - 1)
        if xmin > xmax or ymin > ymax:
            return
        ys, xs = np.mgrid[ymin:ymax + 1, xmin:xmax + 1]
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            t = np.zeros_like(xs, dtype=np.float64)
        else:
            t = ((xs - x0) * dx + (ys - y0) * dy) / L2
            t = np.clip(t, 0.0, 1.0)
        ex = xs - (x0 + t * dx)
        ey = ys - (y0 + t * dy)
        dist = np.sqrt(ex * ex + ey * ey)
        # 1px anti-aliased edge
        alpha = np.clip(r + 0.5 - dist, 0.0, 1.0).astype(np.float32)
        if alpha.max() <= 0:
            return
        region = self.buf[ymin:ymax + 1, xmin:xmax + 1]
        c = np.asarray(color, dtype=np.float32)
        region[:] = region * (1 - alpha[..., None]) + c * alpha[..., None]

    def polyline(self, pts, color, width: float = 1.0):
        for i in range(len(pts) - 1):
            self.line(pts[i], pts[i + 1], color, width)

    # ------------------------------------------------------------ fills

    def fill_polygon(self, contours, color, alpha: float = 1.0):
        """Even-odd fill of one or more contours (pixel-center test)."""
        all_pts = np.concatenate([np.asarray(c, dtype=float) for c in contours])
        xmin = max(int(np.floor(all_pts[:, 0].min())), 0)
        xmax = min(int(np.ceil(all_pts[:, 0].max())), self.w - 1)
        ymin = max(int(np.floor(all_pts[:, 1].min())), 0)
        ymax = min(int(np.ceil(all_pts[:, 1].max())), self.h - 1)
        if xmin > xmax or ymin > ymax:
            return
        ys, xs = np.mgrid[ymin:ymax + 1, xmin:xmax + 1]
        ys = ys + 0.5
        xs = xs + 0.5
        inside = np.zeros(xs.shape, dtype=bool)
        for c in contours:
            p = np.asarray(c, dtype=float)
            q = np.roll(p, -1, axis=0)
            for (x0, y0), (x1, y1) in zip(p, q):
                if y0 == y1:
                    continue
                cond = (y0 <= ys) != (y1 <= ys)
                with np.errstate(divide="ignore", invalid="ignore"):
                    xi = x0 + (ys - y0) * (x1 - x0) / (y1 - y0)
                inside ^= cond & (xs < xi)
        if not inside.any():
            return
        region = self.buf[ymin:ymax + 1, xmin:xmax + 1]
        a = inside.astype(np.float32)[..., None] * alpha
        c = np.asarray(color, dtype=np.float32)
        region[:] = region * (1 - a) + c * a

    # ------------------------------------------------------------ io

    def to_png(self, path: str):
        rgb = (np.clip(self.buf, 0, 1) * 255 + 0.5).astype(np.uint8)
        write_png(path, rgb)


def write_png(path: str, rgb: np.ndarray):
    h, w = rgb.shape[:2]
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
