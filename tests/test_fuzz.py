"""Bounded deterministic fuzz: the behavioral invariants hold under fire.

Invariants (see scripts/fuzz.py for the full campaign tool):
  - every command returns ok or a structured, registered CadError
  - the engine never lets a raw exception escape ('internal' count == 0
    means no bug was caught by the safety net either)
  - the document stays strict-JSON serializable and reloadable
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from fuzz import Fuzzer  # noqa: E402

from modulor.errors import ERROR_CODES  # noqa: E402
from modulor.ops import REGISTRY  # noqa: E402


def test_fuzz_invariants():
    f = Fuzzer(seed=20260611)
    f.op_names = [n for n, e in REGISTRY.items() if e["effects"] != "files"]
    f.run(2500)
    assert not f.findings, \
        f"raw exceptions escaped: {f.findings[0]['cmd']}\n{f.findings[0]['trace']}"
    assert f.codes.get("internal", 0) == 0, \
        "the safety net caught real bugs (code 'internal' raised)"
    unknown = set(f.codes) - set(ERROR_CODES)
    assert not unknown, f"unregistered error codes raised: {unknown}"
    assert f.ok > 100  # the generator still exercises happy paths
