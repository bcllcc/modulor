"""Behavioral fuzzer: hammer the op surface with random and adversarial
commands and enforce the two behavior invariants of the API:

  1. every command returns ok or a *structured* CadError — never a raw
     exception, never a hang;
  2. the document always stays serializable to strict JSON (no NaN/Inf)
     and reloadable.

Run:    python scripts/fuzz.py [iterations] [seed]
CI runs a bounded deterministic slice via tests/test_fuzz.py.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modulor.document import Document  # noqa: E402
from modulor.engine import execute  # noqa: E402
from modulor.errors import ERROR_CODES, CadError  # noqa: E402
from modulor.ops import REGISTRY  # noqa: E402

NASTY_NUMBERS = [0, 1, -1, 0.5, -0.5, 1e-9, 250.0, 3000, -4000, 1e6,
                 9.9e11, 1.1e13, -1.1e13, float("nan"), float("inf"),
                 float("-inf"), 1e308, True]
NASTY_STRINGS = ["", "a", "garbage", "e1", "e999", "E2", "all", "#ff0000",
                 "#zz", "墙体", "bay*2", "level('L1')", "grid_x('A')",
                 "__import__('os').system('x')", "x" * 500, "0", "-5",
                 "1/0", "nan"]
DXF_SAMPLE = os.path.join(os.path.dirname(__file__), "..",
                          "examples", "out", "studio_plan.dxf")


class Fuzzer:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.findings: list[dict] = []
        self.codes: dict[str, int] = {}
        self.ok = 0
        self.slow: list[tuple[float, str]] = []
        self.doc = self._fresh_doc()

    # -------------------------------------------------- seeding

    def _fresh_doc(self) -> Document:
        doc = Document(units=self.rng.choice(["mm", "m"]))
        for cmd in [
            {"op": "set_param", "name": "bay", "value": 4000},
            {"op": "add_level", "name": "L1", "elevation": 0, "height": 3000},
            {"op": "add_circle", "center": [50, 50], "radius": 30, "tag": "c"},
            {"op": "add_rect", "at": [0, 0], "width": 200, "height": 150,
             "tag": "r"},
            {"op": "add_spline", "closed": True, "tag": "s",
             "points": [[300, 0], [400, 80], [500, 0], [400, -80]]},
            {"op": "add_wall", "path": [[0, 300], [800, 300]],
             "thickness": 20, "tag": "w"},
            {"op": "add_box", "at": [600, 0, 0], "size": [100, 80, 60],
             "tag": "b"},
        ]:
            execute(doc, cmd)
        return doc

    # -------------------------------------------------- value generation

    def value_for(self, ptype: str, spec: dict):
        r = self.rng
        if r.random() < 0.22:  # adversarial: wrong type entirely
            return r.choice([None, [], {}, "garbage", -1, 1e13,
                             float("nan"), [[]], {"x": 1}, True])
        if ptype in ("number", "integer"):
            v = r.choice(NASTY_NUMBERS + NASTY_STRINGS[:8])
            if ptype == "integer" and isinstance(v, float) and r.random() < 0.5:
                v = int(v) if abs(v) < 1e9 else v
            return v
        if ptype == "string":
            if spec.get("enum") and r.random() < 0.7:
                return r.choice(spec["enum"])
            return r.choice(NASTY_STRINGS)
        if ptype == "boolean":
            return r.choice([True, False, 1, "true"])
        if ptype == "point2":
            return [r.choice(NASTY_NUMBERS), r.choice(NASTY_NUMBERS)]
        if ptype == "point3":
            n = r.choice([2, 3])
            return [r.choice(NASTY_NUMBERS) for _ in range(n)]
        if ptype == "points":
            n = r.randint(0, 8)
            return [[r.choice(NASTY_NUMBERS), r.choice(NASTY_NUMBERS)]
                    for _ in range(n)]
        if ptype == "select":
            return r.choice([
                "all", "e1", "e999", "E3", ["e1", "e2"], [],
                {"tags": ["c"]}, {"tags": ["nope"]}, {"layers": ["0"]},
                {"types": ["circle", "wall"]}, {"bogus": 1}, 5, None,
            ])
        if ptype == "object":
            return r.choice([
                {}, {"min": [0, 0, 0], "max": [100, 100, 100]},
                {"min": [0, 0], "max": [200, 150]},
                {"min": [float("nan"), 0], "max": [1, 1]},
                {"start": 0, "count": 3, "spacing": 100},
                {"bay": 5000}, {"eye": [1, 1, 1], "target": [0, 0, 0]},
                [0, 100, 200], "garbage", 5,
            ])
        if ptype == "array":
            return r.choice([
                [], [1, 2, 3], ["a"],
                [{"select": "e3", "z": 0}, {"select": "e3", "z": 10}],
                [{"op": "add_circle", "center": [0, 0], "radius": 5}],
                [[0, 0, 0], [10, 10, 10], [20, 0, 30]],
                [{"bogus": True}], "garbage",
            ])
        return None

    def make_command(self) -> dict:
        r = self.rng
        roll = r.random()
        if roll < 0.03:  # totally malformed
            return r.choice([{}, {"op": 5}, {"op": ""}, {"op": "nope"},
                             {"op": ["add_line"]}, {"no_op": 1},
                             {"op": "add_circle ", "radius": 5}])
        name = r.choice(self.op_names)
        e = REGISTRY[name]
        cmd: dict = {"op": name}
        for pname, spec in e["params"].items():
            give = r.random() < (0.92 if spec["required"] else 0.6)
            if give:
                cmd[pname] = self.value_for(spec["type"], spec)
        if r.random() < 0.05:
            cmd["bogus_param"] = 1
        if name == "import_dxf" and r.random() < 0.5:
            cmd["path"] = DXF_SAMPLE
        return cmd

    # -------------------------------------------------- run

    def run(self, iterations: int):
        # everything except file writers (disk churn, not behavior)
        self.op_names = [n for n, e in REGISTRY.items()
                         if e["effects"] != "files"]
        for i in range(iterations):
            cmd = self.make_command()
            t0 = time.perf_counter()
            try:
                execute(self.doc, dict(cmd))
                self.ok += 1
            except CadError as err:
                self.codes[err.code] = self.codes.get(err.code, 0) + 1
            except Exception:
                self.findings.append({"i": i, "cmd": _printable(cmd),
                                      "trace": traceback.format_exc()})
            dt = time.perf_counter() - t0
            if dt > 0.75:
                self.slow.append((round(dt, 2), cmd.get("op", "?")))

            if i % 50 == 49:
                self.check_doc_invariant(i)
            if len(self.doc.entities) > 2500:
                self.doc = self._fresh_doc()

        self.check_doc_invariant(iterations)

    def check_doc_invariant(self, i: int):
        try:
            blob = json.dumps(self.doc.to_dict(), ensure_ascii=False,
                              allow_nan=False)
            Document.from_dict(json.loads(blob))
        except Exception:
            self.findings.append({"i": i, "cmd": "<doc serialization>",
                                  "trace": traceback.format_exc()})
            self.doc = self._fresh_doc()  # keep fuzzing


def _printable(cmd):
    try:
        return json.loads(json.dumps(cmd, default=str))
    except (TypeError, ValueError):
        return str(cmd)


def main():
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    f = Fuzzer(seed)
    t0 = time.perf_counter()
    f.run(iterations)
    unknown_codes = sorted(set(f.codes) - set(ERROR_CODES))
    print(json.dumps({
        "iterations": iterations, "seed": seed,
        "ok": f.ok, "structured_errors": sum(f.codes.values()),
        "by_code": dict(sorted(f.codes.items(), key=lambda kv: -kv[1])),
        "unregistered_codes": unknown_codes,
        "crashes": len(f.findings),
        "slow_ops": f.slow[:10],
        "seconds": round(time.perf_counter() - t0, 1),
    }, ensure_ascii=False, indent=1))
    for finding in f.findings[:12]:
        print("\n--- CRASH at", finding["i"], "---")
        print(json.dumps(finding["cmd"], ensure_ascii=False, default=str)[:300])
        print(finding["trace"][-1200:])
    return 1 if f.findings or unknown_codes else 0


if __name__ == "__main__":
    sys.exit(main())
