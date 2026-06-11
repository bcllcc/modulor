"""Real-world DXF corpus regression.

52 DXF files written by real CAD tools (AutoCAD, BricsCAD, ezdxf, ...),
collected from MIT-licensed sources (see tests/corpus/dxf/ATTRIBUTION.md).
Unlike the roundtrip test — which only proves we can read our own dialect —
this suite holds import_dxf to the open-world standard:

  1. never crash: every file either imports or raises a structured CadError
  2. never lie: imported + skipped accounting is reported for every file
  3. what imports must be usable: serializable document, renderable plan
  4. the corpus as a whole must actually import (not just fail politely)
"""
import glob
import json
import os

import pytest

from modulor import Cad, CadError
from modulor.document import Document

CORPUS = sorted(glob.glob(os.path.join(os.path.dirname(__file__),
                                       "corpus", "dxf", "*.dxf")))


def test_corpus_present():
    assert len(CORPUS) >= 50, "the DXF corpus went missing"


@pytest.mark.parametrize("path", CORPUS,
                         ids=[os.path.basename(p) for p in CORPUS])
def test_corpus_file(path, tmp_path):
    cad = Cad(units="mm")
    try:
        r = cad("import_dxf", path=path)
    except CadError:
        return  # structured rejection (e.g. binary DXF) is a valid outcome

    # honest accounting
    assert "imported" in r and "skipped" in r
    n_imported = sum(r["imported"].values())
    assert len(r["created"]) >= n_imported  # entities per imported record >= 1

    # document invariant: strict JSON roundtrip
    blob = json.dumps(cad.doc.to_dict(), ensure_ascii=False, allow_nan=False)
    Document.from_dict(json.loads(blob))

    # whatever imported must be drawable
    if r["created"]:
        png = str(tmp_path / "corpus.png")
        out = cad("render", path=png, mode="plan", width=400, height=300)
        assert out["path"] == png


def test_corpus_aggregate_yield():
    """The importer must actually extract geometry from the real world,
    not just decline it gracefully."""
    files_ok = 0
    entities = 0
    rejected = []
    for path in CORPUS:
        cad = Cad(units="mm")
        try:
            r = cad("import_dxf", path=path)
        except CadError as e:
            rejected.append((os.path.basename(path), e.code))
            continue
        if r["created"]:
            files_ok += 1
            entities += len(r["created"])
    # Locked to the current importer's real-world yield (39/52, 1514
    # entities). The 13 zero-yield files are all legitimate: header/codepage
    # structure files with no entities at all, deliberately-broken layout
    # test files, ACIS 3DSOLIDs (binary blobs) and ACAD_TABLEs — every one
    # honestly counted in `skipped`. If this assertion fails, an importer
    # change regressed against the real world.
    assert files_ok >= 38, \
        f"only {files_ok}/{len(CORPUS)} files yielded entities; " \
        f"rejected: {rejected[:10]}"
    assert entities >= 1400, f"corpus yielded only {entities} entities"
