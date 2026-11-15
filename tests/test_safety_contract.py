import csv
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

import api.risk_api as risk_api


def test_loader_maps_checked_in_csv_schema(tmp_path: Path):
    """The runtime must accept the documented compound_a/source_ids fields."""
    with (tmp_path / "interactions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["compound_a", "compound_b", "severity", "evidence_grade", "mechanism_tags", "source_ids"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "compound_a": "alpha",
                "compound_b": "beta",
                "severity": "Moderate",
                "evidence_grade": "B",
                "mechanism_tags": "additive;pharmacodynamic",
                "source_ids": "source:one;source:two",
            }
        )

    records = risk_api.load_interactions(tmp_path)

    assert len(records) == 1
    assert records[0]["a"] == "alpha"
    assert records[0]["b"] == "beta"
    assert records[0]["evidence"] == "B"
    assert records[0]["sources"] == ["source:one", "source:two"]
    assert records[0]["mechanism"] == ["additive", "pharmacodynamic"]


def test_known_pair_without_record_is_explicitly_not_assessed(monkeypatch):
    original_compounds = risk_api.COMPOUNDS
    original_interactions = risk_api.INTERACTIONS
    original_sources = risk_api.SOURCES
    try:
        risk_api.COMPOUNDS = {
            "alpha": {"id": "alpha", "name": "Alpha", "synonyms": []},
            "beta": {"id": "beta", "name": "Beta", "synonyms": []},
        }
        risk_api.INTERACTIONS = []
        risk_api.SOURCES = {}
        risk_api.build_compound_indexes()
        risk_api.build_interaction_lookup()

        result = risk_api.interaction("alpha", "beta")

        assert result["assessment"] == "not_assessed"
        assert result["interaction"] is None
        assert "does not mean" in result["message"]
    finally:
        risk_api.COMPOUNDS = original_compounds
        risk_api.INTERACTIONS = original_interactions
        risk_api.SOURCES = original_sources
        risk_api.build_compound_indexes()
        risk_api.build_interaction_lookup()


def test_stack_rejects_duplicate_resolved_compounds():
    with pytest.raises(HTTPException) as captured:
        risk_api.check_stack(risk_api.StackRequest(compounds=["caffeine", "Caffeine"]))
    assert captured.value.status_code == 422
    assert captured.value.detail == "A stack cannot include the same compound more than once"


def test_label_candidate_cannot_be_scored():
    with pytest.raises(ValueError, match="Only assessed_interaction"):
        risk_api.compute_risk(
            {
                "record_kind": "openfda_label_candidate",
                "severity": "Severe",
                "evidence": "A",
            }
        )


def test_label_candidates_are_never_promoted_to_pair_or_stack_results():
    original_compounds = risk_api.COMPOUNDS
    original_interactions = risk_api.INTERACTIONS
    original_sources = risk_api.SOURCES
    original_candidates = risk_api.LABEL_CANDIDATES
    try:
        risk_api.COMPOUNDS = {
            "alpha": {"id": "alpha", "name": "Alpha", "synonyms": []},
            "beta": {"id": "beta", "name": "Beta", "synonyms": []},
        }
        risk_api.INTERACTIONS = []
        risk_api.SOURCES = {"openfda:set": {"id": "openfda:set", "citation": "Label"}}
        risk_api.LABEL_CANDIDATES = [
            {
                "candidate_id": "openfda:alpha:beta:set",
                "record_kind": "openfda_label_candidate",
                "review_status": "unreviewed",
                "subject_compound_id": "alpha",
                "mentioned_compound_id": "beta",
                "source_id": "openfda:set",
            }
        ]
        risk_api.build_compound_indexes()
        risk_api.build_interaction_lookup()

        candidates = risk_api.list_label_candidates("alpha")
        pair = risk_api.interaction("alpha", "beta")
        stack = risk_api.check_stack(risk_api.StackRequest(compounds=["alpha", "beta"]))

        assert candidates["status"] == "unverified_label_candidates"
        assert candidates["count"] == 1
        assert pair["assessment"] == "not_assessed"
        assert stack["coverage"] == {"total_pairs": 1, "assessed_pairs": 0, "not_assessed_pairs": 1}
    finally:
        risk_api.COMPOUNDS = original_compounds
        risk_api.INTERACTIONS = original_interactions
        risk_api.SOURCES = original_sources
        risk_api.LABEL_CANDIDATES = original_candidates
        risk_api.build_compound_indexes()
        risk_api.build_interaction_lookup()


@pytest.mark.anyio("asyncio")
async def test_spa_fallback_blocks_traversal_but_serves_assets(monkeypatch, tmp_path: Path):
    frontend_dist = tmp_path / "frontend_dist"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text("SPA INDEX", encoding="utf-8")
    (frontend_dist / "asset.txt").write_text("SAFE ASSET", encoding="utf-8")
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    (api_dir / "risk_api.py").write_text("PRIVATE API", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("PRIVATE REQUIREMENTS", encoding="utf-8")
    monkeypatch.setattr(risk_api, "FRONTEND_DIST", frontend_dist)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=risk_api.app),
        base_url="http://testserver",
    ) as client:
        for path in (
            "/%2e%2e/api/risk_api.py",
            "/..%2fapi%2frisk_api.py",
            "/%2e%2e%2frequirements.txt",
            "/%2e%2e%5capi%5crisk_api.py",
        ):
            response = await client.get(path)
            assert response.status_code in {200, 404}
            assert "PRIVATE API" not in response.text
            assert "PRIVATE REQUIREMENTS" not in response.text

        asset = await client.get("/asset.txt")
        assert asset.status_code == 200
        assert asset.text == "SAFE ASSET"

        unknown_route = await client.get("/client-side-route")
        assert unknown_route.status_code == 200
        assert unknown_route.text == "SPA INDEX"


def _assessed_record(a: str, b: str, severity: str = "Severe") -> dict:
    return {
        "record_kind": "assessed_interaction",
        "a": a,
        "b": b,
        "bidirectional": True,
        "mechanism": [],
        "severity": severity,
        "evidence": "A",
        "sources": [],
    }


def _set_runtime_data(monkeypatch, interactions):
    compound_ids = {"alpha", "beta", "gamma"}
    monkeypatch.setattr(
        risk_api,
        "COMPOUNDS",
        {
            compound_id: {
                "id": compound_id,
                "name": compound_id.title(),
                "synonyms": [],
            }
            for compound_id in compound_ids
        },
    )
    monkeypatch.setattr(risk_api, "INTERACTIONS", interactions)
    monkeypatch.setattr(risk_api, "SOURCES", {})
    risk_api.build_compound_indexes()
    risk_api.build_interaction_lookup()


def test_stack_assessment_reports_unassessed_pair_coverage(monkeypatch):
    _set_runtime_data(monkeypatch, [])
    none_assessed = risk_api.check_stack(
        risk_api.StackRequest(compounds=["alpha", "beta"])
    )
    assert none_assessed["assessment"] == "not_assessed"
    assert none_assessed["coverage"] == {
        "total_pairs": 1,
        "assessed_pairs": 0,
        "not_assessed_pairs": 1,
    }
    assert "does not mean" in none_assessed["message"]
    assert none_assessed["not_assessed_pairs_detail"] == [{"a": "alpha", "b": "beta"}]

    _set_runtime_data(monkeypatch, [_assessed_record("alpha", "beta")])
    partially_assessed = risk_api.check_stack(
        risk_api.StackRequest(compounds=["alpha", "beta", "gamma"])
    )
    assert partially_assessed["assessment"] == "partial"
    assert partially_assessed["coverage"] == {
        "total_pairs": 3,
        "assessed_pairs": 1,
        "not_assessed_pairs": 2,
    }
    assert "does not mean" in partially_assessed["message"]
    assert partially_assessed["not_assessed_pairs_detail"] == [
        {"a": "alpha", "b": "gamma"},
        {"a": "beta", "b": "gamma"},
    ]

    _set_runtime_data(
        monkeypatch,
        [
            _assessed_record("alpha", "beta"),
            _assessed_record("alpha", "gamma"),
            _assessed_record("beta", "gamma"),
        ],
    )
    fully_assessed = risk_api.check_stack(
        risk_api.StackRequest(compounds=["alpha", "beta", "gamma"])
    )
    assert fully_assessed["assessment"] == "assessed"
    assert "message" not in fully_assessed
    assert fully_assessed["not_assessed_pairs_detail"] == []


def test_invalid_assessed_labels_are_not_scored_or_returned(monkeypatch):
    for severity in ("Contraindicated", "", None):
        with pytest.raises(ValueError, match="severity"):
            risk_api.compute_risk(
                {
                    "record_kind": "assessed_interaction",
                    "severity": severity,
                    "evidence": "A",
                    "mechanism": [],
                }
            )

    record = _assessed_record("alpha", "beta")
    _set_runtime_data(monkeypatch, [record])
    record["severity"] = "Contraindicated"

    pair = risk_api.interaction("alpha", "beta")
    stack = risk_api.check_stack(risk_api.StackRequest(compounds=["alpha", "beta"]))

    assert pair["assessment"] == "not_assessed"
    assert pair["risk_score"] is None
    assert stack["assessment"] == "not_assessed"
    assert stack["coverage"]["assessed_pairs"] == 0
    assert stack["not_assessed_pairs_detail"] == [{"a": "alpha", "b": "beta"}]


def test_interaction_lookup_keeps_highest_scoring_duplicate(monkeypatch):
    for first, second in (("Severe", "Mild"), ("Mild", "Severe")):
        _set_runtime_data(
            monkeypatch,
            [
                _assessed_record("alpha", "beta", first),
                _assessed_record("alpha", "beta", second),
            ],
        )
        assert risk_api._INTERACTION_LOOKUP[("alpha", "beta")]["severity"] == "Severe"
        assert risk_api._INTERACTION_LOOKUP[("beta", "alpha")]["severity"] == "Severe"


def test_interaction_rejects_duplicate_resolved_compounds(monkeypatch):
    _set_runtime_data(monkeypatch, [])
    with pytest.raises(HTTPException) as captured:
        risk_api.interaction("alpha", "Alpha")
    assert captured.value.status_code == 422
    assert "different compounds" in captured.value.detail


@pytest.fixture
def isolated_data_dir(monkeypatch, tmp_path: Path):
    snapshot = {
        "compounds": risk_api.COMPOUNDS,
        "interactions": risk_api.INTERACTIONS,
        "sources": risk_api.SOURCES,
        "candidates": risk_api.LABEL_CANDIDATES,
        "dataset_mode": risk_api.DATASET_MODE,
        "mechanisms": risk_api.MECHANISM_DELTAS,
        "weights": risk_api.WEIGHTS,
        "severity": risk_api.SEVERITY_MAP,
        "evidence": risk_api.EVIDENCE_MAP,
        "formula": risk_api.RISK_FORMULA,
        "formula_source": risk_api.FORMULA_SOURCE,
    }
    monkeypatch.setattr(risk_api, "DATA_DIR", tmp_path)
    risk_api.reset_health_state()
    yield tmp_path
    risk_api.COMPOUNDS = snapshot["compounds"]
    risk_api.INTERACTIONS = snapshot["interactions"]
    risk_api.SOURCES = snapshot["sources"]
    risk_api.LABEL_CANDIDATES = snapshot["candidates"]
    risk_api.DATASET_MODE = snapshot["dataset_mode"]
    risk_api.MECHANISM_DELTAS = snapshot["mechanisms"]
    risk_api.WEIGHTS = snapshot["weights"]
    risk_api.SEVERITY_MAP = snapshot["severity"]
    risk_api.EVIDENCE_MAP = snapshot["evidence"]
    risk_api.RISK_FORMULA = snapshot["formula"]
    risk_api.FORMULA_SOURCE = snapshot["formula_source"]
    risk_api.build_compound_indexes()
    risk_api.build_interaction_lookup()
    risk_api.reset_health_state()


def _write_valid_assessed_files(directory: Path, interactions):
    with (directory / "compounds.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "name"])
        writer.writeheader()
        writer.writerows(
            [{"id": "alpha", "name": "Alpha"}, {"id": "beta", "name": "Beta"}]
        )
    with (directory / "sources.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "citation"])
        writer.writeheader()
        writer.writerow({"id": "source:one", "citation": "Primary source"})
    fieldnames = [
        "a",
        "b",
        "severity",
        "evidence",
        "sources",
        "record_kind",
        "review_status",
    ]
    with (directory / "interactions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(interactions)


def test_load_data_excludes_raw_candidate_interactions(isolated_data_dir):
    _write_valid_assessed_files(
        isolated_data_dir,
        [
            {
                "a": "alpha",
                "b": "beta",
                "severity": "Moderate",
                "evidence": "B",
                "sources": "source:one",
                "record_kind": "assessed_interaction",
                "review_status": "",
            },
            {
                "a": "alpha",
                "b": "beta",
                "severity": "Severe",
                "evidence": "A",
                "sources": "source:one",
                "record_kind": "openfda_label_candidate",
                "review_status": "unreviewed",
            },
        ],
    )

    risk_api.load_data()

    assert len(risk_api.INTERACTIONS) == 1
    assert risk_api.INTERACTIONS[0]["severity"] == "Moderate"
    assert risk_api.health()["status"] == "degraded"


def test_load_data_excludes_unscoreable_interactions(isolated_data_dir):
    _write_valid_assessed_files(
        isolated_data_dir,
        [
            {
                "a": "alpha",
                "b": "beta",
                "severity": "Contraindicated",
                "evidence": "A",
                "sources": "source:one",
                "record_kind": "assessed_interaction",
                "review_status": "",
            }
        ],
    )

    risk_api.load_data()

    assert risk_api.INTERACTIONS == []
    assert risk_api.health()["status"] == "degraded"
    assert risk_api.interaction("alpha", "beta")["assessment"] == "not_assessed"


def test_load_data_reports_empty_invalid_and_corrupt_loaders(isolated_data_dir, monkeypatch):
    cases = [
        ("empty", "compounds.csv", "id,name\n"),
        ("schema", "sources.csv", "citation\n"),
        ("corrupt_json", "compounds.json", "{"),
    ]
    for name, target, content in cases:
        case_dir = isolated_data_dir / name
        case_dir.mkdir()
        _write_valid_assessed_files(
            case_dir,
            [
                {
                    "a": "alpha",
                    "b": "beta",
                    "severity": "Moderate",
                    "evidence": "B",
                    "sources": "source:one",
                    "record_kind": "assessed_interaction",
                    "review_status": "",
                }
            ],
        )
        (case_dir / target).write_text(content, encoding="utf-8")
        monkeypatch.setattr(risk_api, "DATA_DIR", case_dir)
        risk_api.reset_health_state()
        risk_api.load_data()
        assert risk_api.health()["status"] == "degraded"
        assert any(issue["source"] == target for issue in risk_api.health()["issues"])


def test_ambiguous_alias_fails_closed(monkeypatch):
    original_compounds = risk_api.COMPOUNDS
    original_interactions = risk_api.INTERACTIONS
    try:
        risk_api.COMPOUNDS = {
            "alpha": {"id": "alpha", "name": "Alpha", "aliases": ["shared"]},
            "beta": {"id": "beta", "name": "Beta", "aliases": ["shared"]},
        }
        risk_api.INTERACTIONS = []
        risk_api.build_compound_indexes()
        risk_api.build_interaction_lookup()

        assert risk_api.resolve_compound("shared") is None
        assert risk_api.resolve_compound("alpha") == "alpha"
        assert risk_api.resolve_compound("beta") == "beta"
        with pytest.raises(HTTPException) as captured:
            risk_api.interaction("shared", "alpha")
        assert captured.value.status_code == 404
    finally:
        risk_api.COMPOUNDS = original_compounds
        risk_api.INTERACTIONS = original_interactions
        risk_api.build_compound_indexes()
        risk_api.build_interaction_lookup()


def test_health_issues_do_not_expose_loader_paths(isolated_data_dir):
    _write_valid_assessed_files(
        isolated_data_dir,
        [
            {
                "a": "alpha",
                "b": "beta",
                "severity": "Moderate",
                "evidence": "B",
                "sources": "source:one",
                "record_kind": "assessed_interaction",
                "review_status": "",
            }
        ],
    )
    (isolated_data_dir / "compounds.csv").write_text("", encoding="utf-8")

    risk_api.load_data()

    rendered_issues = str(risk_api.health()["issues"])
    assert str(isolated_data_dir) not in rendered_issues
    assert "\\" not in rendered_issues
    assert all(set(issue) == {"source", "code", "count"} for issue in risk_api.health()["issues"])


def test_invalid_rules_remain_degraded_after_data_reload(isolated_data_dir):
    rules_path = isolated_data_dir / "rules.yaml"
    rules_path.write_text("weights:\n  severity: not-a-number\n", encoding="utf-8")
    risk_api.apply_rules(str(rules_path))
    _write_valid_assessed_files(
        isolated_data_dir,
        [
            {
                "a": "alpha",
                "b": "beta",
                "severity": "Moderate",
                "evidence": "B",
                "sources": "source:one",
                "record_kind": "assessed_interaction",
                "review_status": "",
            }
        ],
    )

    risk_api.load_data()

    assert risk_api.WEIGHTS == risk_api.DEFAULT_WEIGHTS
    assert risk_api.health()["status"] == "degraded"
    assert any(
        issue["source"] == "rules.yaml" and issue["code"] == "invalid_rules_config"
        for issue in risk_api.health()["issues"]
    )


def test_empty_candidate_dataset_stays_candidate_only_and_is_degraded(isolated_data_dir):
    _write_valid_assessed_files(isolated_data_dir, [])
    candidate_fields = [
        "candidate_id",
        "record_kind",
        "review_status",
        "subject_compound_id",
        "mentioned_compound_id",
        "mentioned_text",
        "section",
        "source_id",
        "set_id",
        "effective_time",
        "source_url",
        "extracted_text",
        "extraction_method",
        "retrieved_at",
        "rights_status",
    ]
    with (isolated_data_dir / "label_candidates.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        csv.DictWriter(handle, fieldnames=candidate_fields).writeheader()

    risk_api.load_data()

    health = risk_api.health()
    assert health["dataset_mode"] == "candidate_only"
    assert health["label_candidates_loaded"] == 0
    assert health["status"] == "degraded"
    assert any(issue["source"] == "label_candidates.csv" for issue in health["issues"])
