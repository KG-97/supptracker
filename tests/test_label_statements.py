import copy
import csv
import json
import shutil
from pathlib import Path
from typing import Any

import httpx
import pytest

import api.label_statements as label_statements
import api.risk_api as risk_api


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "data" / "openfda_supplement_statements"
FORBIDDEN_KEYS = {"severity", "score", "risk", "safe", "mechanism", "evidence"}
FORBIDDEN_PHRASES = (
    "no interaction",
    "no known interaction",
    "none found",
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=risk_api.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client


@pytest.fixture(autouse=True)
def restore_statement_dataset():
    label_statements.reload_label_statements(DATASET_DIR)
    yield
    label_statements.reload_label_statements(DATASET_DIR)


def _copy_dataset(tmp_path: Path) -> Path:
    destination = tmp_path / "statements"
    shutil.copytree(DATASET_DIR, destination)
    return destination


def _assert_no_forbidden_generated_content(value: Any, key: str = "") -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            assert child_key.casefold() not in FORBIDDEN_KEYS
            _assert_no_forbidden_generated_content(child_value, child_key)
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_forbidden_generated_content(item, key)
        return
    if isinstance(value, str) and key not in {"sentence", "disclaimer"}:
        lower = value.casefold()
        assert not any(phrase in lower for phrase in FORBIDDEN_PHRASES)


def test_loader_matches_checked_in_manifest_counts():
    dataset = label_statements.load_label_statements(DATASET_DIR)
    manifest = json.loads((DATASET_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert dataset["status"] == "available"
    assert len(dataset["statements"]) == manifest["counts"]["statements"]
    assert len(dataset["pairs"]) == manifest["counts"]["distinct_pairs"]
    assert len({row["supplement_id"] for row in dataset["statements"]}) == (
        manifest["counts"]["distinct_supplements"]
    )
    assert len({row["drug_id"] for row in dataset["statements"]}) == (
        manifest["counts"]["distinct_drugs"]
    )


@pytest.mark.anyio("asyncio")
async def test_statement_endpoints_return_verbatim_records_and_not_assessed(client):
    summary = await client.get("/api/label-statements/summary")
    assert summary.status_code == 200
    summary_data = summary.json()
    assert summary_data["status"] == "available"
    # Read from the manifest, not a literal, so a dictionary improvement does not break the test.
    manifest = json.loads((DATASET_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert summary_data["counts"]["statements"] == manifest["counts"]["statements"]
    assert summary_data["disclaimer"] == label_statements.DISCLAIMER
    assert all(
        "is_group_term" in supplement
        for supplement in summary_data["supplements"]
    )

    listing = await client.get(
        "/api/label-statements",
        params={"supplement": "antacids", "drug": "acalabrutinib", "limit": 2},
    )
    assert listing.status_code == 200
    listing_data = listing.json()
    assert listing_data["total"] == 3
    assert listing_data["disclaimer"] == label_statements.DISCLAIMER
    item = listing_data["items"][0]
    assert item["record_kind"] == "fda_label_statement"
    assert item["is_group_term"] is True
    assert item["label_url"].endswith(item["set_id"])
    assert item["sentence"] in {
        row["sentence"]
        for row in label_statements.LABEL_STATEMENTS["statements"]
    }

    pair = await client.get(
        "/api/label-statements/pair",
        params={"supplement": "antacids", "drug": "acalabrutinib"},
    )
    assert pair.status_code == 200
    assert pair.json()["total"] == 3
    assert pair.json()["disclaimer"] == label_statements.DISCLAIMER

    no_match = await client.get(
        "/api/label-statements/pair",
        params={"supplement": "not-a-supplement", "drug": "not-a-drug"},
    )
    assert no_match.status_code == 200
    assert no_match.json()["assessment"] == "not_assessed"
    assert no_match.json()["disclaimer"] == label_statements.DISCLAIMER

    filtered_no_match = await client.get(
        "/api/label-statements",
        params={"q": "this text does not occur in an FDA label"},
    )
    assert filtered_no_match.status_code == 200
    assert filtered_no_match.json()["assessment"] == "not_assessed"
    assert filtered_no_match.json()["disclaimer"] == label_statements.DISCLAIMER


@pytest.mark.anyio("asyncio")
async def test_statement_responses_have_no_generated_clinical_fields_or_claims(client):
    responses = [
        await client.get("/api/label-statements/summary"),
        await client.get(
            "/api/label-statements",
            params={"supplement": "antacids", "drug": "acalabrutinib"},
        ),
        await client.get(
            "/api/label-statements/pair",
            params={"supplement": "not-a-supplement", "drug": "not-a-drug"},
        ),
    ]

    for response in responses:
        assert response.status_code == 200
        payload = response.json()
        assert payload["disclaimer"] == label_statements.DISCLAIMER
        _assert_no_forbidden_generated_content(payload)


def test_scoring_results_are_identical_when_statement_corpus_is_unavailable(
    tmp_path: Path,
):
    original_compounds = risk_api.COMPOUNDS
    original_interactions = risk_api.INTERACTIONS
    original_sources = risk_api.SOURCES
    try:
        risk_api.COMPOUNDS = {
            "caffeine": {"id": "caffeine", "name": "Caffeine", "synonyms": []},
            "aspirin": {"id": "aspirin", "name": "Aspirin", "synonyms": []},
            "magnesium": {"id": "magnesium", "name": "Magnesium", "synonyms": []},
        }
        risk_api.INTERACTIONS = [
            {
                "record_kind": "assessed_interaction",
                "id": "caffeine-aspirin",
                "a": "caffeine",
                "b": "aspirin",
                "bidirectional": True,
                "mechanism": ["additive"],
                "severity": "Moderate",
                "evidence": "B",
                "effect": "",
                "action": "",
                "sources": ["s1"],
            },
            {
                "record_kind": "assessed_interaction",
                "id": "caffeine-magnesium",
                "a": "caffeine",
                "b": "magnesium",
                "bidirectional": True,
                "mechanism": ["pharmacodynamic"],
                "severity": "Mild",
                "evidence": "C",
                "effect": "",
                "action": "",
                "sources": ["s1"],
            },
            {
                "record_kind": "assessed_interaction",
                "id": "aspirin-magnesium",
                "a": "aspirin",
                "b": "magnesium",
                "bidirectional": True,
                "mechanism": ["pharmacokinetic"],
                "severity": "Severe",
                "evidence": "A",
                "effect": "",
                "action": "",
                "sources": ["s1"],
            },
        ]
        risk_api.SOURCES = {"s1": {"id": "s1", "citation": "Test source"}}
        risk_api.build_compound_indexes()
        risk_api.build_interaction_lookup()

        label_statements.reload_label_statements(DATASET_DIR)
        loaded_results = [
            risk_api.interaction("caffeine", "aspirin"),
            risk_api.interaction("caffeine", "magnesium"),
            risk_api.interaction("aspirin", "magnesium"),
            risk_api.check_stack(
                risk_api.StackRequest(
                    compounds=["caffeine", "aspirin", "magnesium"]
                )
            ),
        ]

        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()
        label_statements.reload_label_statements(empty_folder)
        unavailable_results = [
            risk_api.interaction("caffeine", "aspirin"),
            risk_api.interaction("caffeine", "magnesium"),
            risk_api.interaction("aspirin", "magnesium"),
            risk_api.check_stack(
                risk_api.StackRequest(
                    compounds=["caffeine", "aspirin", "magnesium"]
                )
            ),
        ]

        assert unavailable_results == loaded_results
    finally:
        risk_api.COMPOUNDS = original_compounds
        risk_api.INTERACTIONS = original_interactions
        risk_api.SOURCES = original_sources
        risk_api.build_compound_indexes()
        risk_api.build_interaction_lookup()


@pytest.mark.anyio("asyncio")
async def test_loader_fails_closed_and_existing_endpoints_continue(
    tmp_path: Path, client
):
    cases = []

    missing_folder = tmp_path / "missing"
    cases.append(missing_folder)

    missing_column = _copy_dataset(tmp_path / "missing-column")
    statement_file = missing_column / "statements.csv"
    with statement_file.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fieldnames = [
        field for field in rows[0] if field != "sentence"
    ]
    with statement_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            [{key: value for key, value in row.items() if key != "sentence"} for row in rows]
        )
    cases.append(missing_column)

    wrong_kind = _copy_dataset(tmp_path / "wrong-kind")
    statement_file = wrong_kind / "statements.csv"
    with statement_file.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    rows[0]["record_kind"] = "wrong_kind"
    with statement_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    cases.append(wrong_kind)

    duplicate_id = _copy_dataset(tmp_path / "duplicate-id")
    statement_file = duplicate_id / "statements.csv"
    with statement_file.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    rows[1]["statement_id"] = rows[0]["statement_id"]
    with statement_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    cases.append(duplicate_id)

    # Added by Claude Code 2026-11-15: a non-numeric label count used to raise while loading.
    bad_count = _copy_dataset(tmp_path / "bad-label-count")
    statement_file = bad_count / "statements.csv"
    with statement_file.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    rows[0]["label_count"] = "many"
    with statement_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    cases.append(bad_count)

    for directory in cases:
        dataset = label_statements.reload_label_statements(directory)
        assert dataset["status"] == "unavailable"
        assert dataset["reason"]
        assert dataset["statements"] == []

        response = await client.get("/api/label-statements")
        assert response.status_code == 200
        assert response.json()["status"] == "unavailable"
        assert response.json()["items"] == []
        assert response.json()["assessment"] == "not_assessed"

        assert risk_api.health()["status"] in {"healthy", "degraded"}
        assert isinstance(risk_api.list_compounds()["compounds"], list)
