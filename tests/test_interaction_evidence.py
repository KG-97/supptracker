"""The assessed interaction list loads whole, and every re-sourced row shows its evidence.

data/interaction_evidence.csv records, for each re-sourced interaction, the exact
sentence from each cited source that supports it (FDA label, NCCIH fact sheet or
PubMed abstract). The quotes were checked word-for-word against the source text
when the rows were written on 2026-11-19.
"""
import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"
VERIFIED_PREFIXES = ("dailymed:", "nccih:", "pubmed:")


def _rows(name):
    with open(DATA / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _pair(a, b):
    return tuple(sorted((a, b)))


@pytest.fixture(scope="module")
def interactions():
    return {_pair(r["compound_a"], r["compound_b"]): r for r in _rows("interactions.csv")}


@pytest.fixture(scope="module")
def evidence():
    return _rows("interaction_evidence.csv")


def test_every_interaction_pair_is_listed_once():
    pairs = [_pair(r["compound_a"], r["compound_b"]) for r in _rows("interactions.csv")]
    assert len(pairs) == len(set(pairs))


def test_evidence_rows_point_at_a_cited_source(interactions, evidence):
    source_ids = {r["id"] for r in _rows("sources.csv")}
    for row in evidence:
        record = interactions.get(_pair(row["compound_a"], row["compound_b"]))
        assert record is not None, row
        assert row["source_id"] in record["source_ids"].split(";"), row
        assert row["source_id"] in source_ids, row
        assert len(row["quote"].strip()) >= 20, row


def test_every_source_a_resourced_row_cites_has_a_quote(interactions, evidence):
    # Rows with evidence are the ones re-sourced on 2026-11-19. The 23 rows that were
    # already loading before then cite Examine pages and predate the evidence file.
    quoted = {(_pair(r["compound_a"], r["compound_b"]), r["source_id"]) for r in evidence}
    resourced = {pair for pair, _ in quoted}
    assert len(resourced) == 45
    for pair in resourced:
        for source_id in interactions[pair]["source_ids"].split(";"):
            if source_id.startswith(VERIFIED_PREFIXES):
                assert (pair, source_id) in quoted, (pair, source_id)


def test_assessed_dataset_loads_without_excluding_records(monkeypatch):
    import api.risk_api as risk_api

    monkeypatch.setattr(risk_api, "DATA_DIR", DATA)
    risk_api.load_data()
    try:
        loaded = {_pair(r["a"], r["b"]) for r in risk_api.INTERACTIONS}
        assert len(loaded) == len(_rows("interactions.csv"))
        failures = [issue for issue in risk_api.DATA_HEALTH.snapshot()["issues"]]
        assert not failures, failures
        # The amlodipine label says grapefruit juice has no effect on amlodipine exposure,
        # so that former record is gone and the pair is left unassessed.
        assert _pair("amlodipine", "grapefruit") not in loaded
        assert _pair("simvastatin", "grapefruit") in loaded
    finally:
        monkeypatch.undo()
        risk_api.load_data()
