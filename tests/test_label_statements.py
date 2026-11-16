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


@pytest.mark.anyio("asyncio")
async def test_lookup_points_free_text_names_at_verbatim_statements(client):
    response = await client.get(
        "/api/label-statements/lookup",
        params=[("names", "Caffeine"), ("names", "ciprofloxacin")],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    # Label text is never an assessment, even when statements are found.
    assert payload["assessment"] == "not_assessed"
    assert payload["message"] == label_statements.LOOKUP_FOUND_MESSAGE
    assert payload["disclaimer"] == label_statements.DISCLAIMER
    assert payload["total_pairs"] >= 1
    corpus = {row["sentence"] for row in label_statements.LABEL_STATEMENTS["statements"]}
    for group in payload["pairs"]:
        assert group["supplement_id"] == "caffeine"
        assert "ciprofloxacin" in group["drug_id"]
        assert group["total"] == len(group["items"]) >= 1
        assert all(item["sentence"] in corpus for item in group["items"])
    _assert_no_forbidden_generated_content(payload)


@pytest.mark.anyio("asyncio")
async def test_lookup_resolves_plain_names_by_whole_words_only(client):
    response = await client.get(
        "/api/label-statements/lookup",
        params=[
            ("names", "calcium"),
            ("names", "warfarin"),
            ("names", "ciprofloxacin"),
            ("names", "war"),
            ("names", "wa"),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["assessment"] == "not_assessed"
    names = {entry["input"]: entry for entry in payload["names"]}
    assert "calcium" in {item["supplement_id"] for item in names["calcium"]["supplements"]}
    assert names["calcium"]["drug_total"] == 0
    assert names["warfarin"]["drug_total"] >= 1
    assert all(item["drug_id"].startswith("warfarin") for item in names["warfarin"]["drugs"])
    assert any(item["drug_id"] == "ciprofloxacin" for item in names["ciprofloxacin"]["drugs"])
    # A fragment of a name must not resolve to anything.
    assert names["war"]["drug_total"] == 0 and names["war"]["supplements"] == []
    assert names["wa"]["drug_total"] == 0 and names["wa"]["supplements"] == []


@pytest.mark.anyio("asyncio")
async def test_lookup_does_not_resolve_generic_components_as_drugs(client):
    response = await client.get(
        "/api/label-statements/lookup",
        params=[
            ("names", "water"),
            ("names", "water pills"),
            ("names", "sodium"),
            ("names", "potassium"),
            ("names", "niacin"),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["assessment"] == "not_assessed"
    names = {entry["input"]: entry for entry in payload["names"]}
    for name in ("water", "water pills", "sodium", "potassium"):
        assert names[name]["drug_total"] == 0
        assert names[name]["drugs"] == []


@pytest.mark.anyio("asyncio")
async def test_lookup_marks_combination_product_matches(client):
    response = await client.get(
        "/api/label-statements/lookup",
        params=[("names", "potassium"), ("names", "spironolactone")],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["assessment"] == "not_assessed"

    drugs = {item["drug_id"]: item for item in payload["names"][1]["drugs"]}
    assert drugs["hydrochlorothiazide+spironolactone"]["combination_product"] is True

    pair = next(
        item
        for item in payload["pairs"]
        if item["drug_id"] == "hydrochlorothiazide+spironolactone"
    )
    assert pair["combination_product"] is True


@pytest.mark.anyio("asyncio")
async def test_lookup_without_a_match_is_not_assessed_and_never_reassuring(client):
    response = await client.get(
        "/api/label-statements/lookup",
        params=[("names", "not-a-supplement"), ("names", "not-a-drug")],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["assessment"] == "not_assessed"
    assert payload["total_pairs"] == 0 and payload["pairs"] == []
    assert payload["message"] == label_statements.LOOKUP_NONE_MESSAGE
    assert "does not mean the combination is safe" in payload["message"]
    _assert_no_forbidden_generated_content(payload)


@pytest.mark.anyio("asyncio")
async def test_lookup_rejects_bad_input_and_fails_closed_when_unavailable(client, tmp_path):
    too_many = await client.get(
        "/api/label-statements/lookup",
        params=[("names", f"name {number}") for number in range(21)],
    )
    assert too_many.status_code == 422
    assert too_many.json()["assessment"] == "not_assessed"
    blank = await client.get("/api/label-statements/lookup", params=[("names", "   ")])
    assert blank.status_code == 422
    assert blank.json()["assessment"] == "not_assessed"
    too_long = await client.get("/api/label-statements/lookup", params=[("names", "x" * 121)])
    assert too_long.status_code == 422
    assert too_long.json()["assessment"] == "not_assessed"

    label_statements.reload_label_statements(tmp_path / "missing")
    unavailable = await client.get(
        "/api/label-statements/lookup",
        params=[("names", "caffeine"), ("names", "ciprofloxacin")],
    )
    assert unavailable.status_code == 200
    assert unavailable.json()["status"] == "unavailable"
    assert unavailable.json()["assessment"] == "not_assessed"
    assert unavailable.json()["pairs"] == []


@pytest.mark.anyio("asyncio")
async def test_supplement_filter_ignores_letter_case(client):
    lower = await client.get("/api/label-statements", params={"supplement": "melatonin"})
    mixed = await client.get("/api/label-statements", params={"supplement": " Melatonin "})
    assert lower.json()["total"] == mixed.json()["total"] > 0
    pair = await client.get(
        "/api/label-statements/pair",
        params={"supplement": "Antacids", "drug": "Acalabrutinib"},
    )
    assert pair.json()["total"] == 3


def test_lookup_works_without_the_optional_dictionary(tmp_path):
    dataset = _copy_dataset(tmp_path)
    (dataset / "supplement_terms.json").unlink()
    label_statements.reload_label_statements(dataset)
    payload = label_statements.label_statements_lookup(names=["caffeine", "ciprofloxacin"])
    assert payload["total_pairs"] >= 1
    assert payload["assessment"] == "not_assessed"


@pytest.mark.anyio("asyncio")
async def test_lookup_accepts_everyday_spellings_as_exact_aliases_only(client):
    spellings = {
        "grapefruit juice": "grapefruit",
        "CoQ10": "coenzyme-q10",
        "Co-Q10": "coenzyme-q10",
        "K2": "vitamin-k",
        "D3": "vitamin-d",
        "cholecalciferol": "vitamin-d",
        "B6": "vitamin-b6",
        "b12": "vitamin-b12",
        "vitamin B3": "niacin",
        "5 HTP": "tryptophan-5htp",
        "5htp": "tryptophan-5htp",
        "L-tryptophan": "tryptophan-5htp",
        "Saint John's wort": "st-johns-wort",
        "retinol": "vitamin-a",
    }
    response = await client.get(
        "/api/label-statements/lookup", params=[("names", name) for name in spellings]
    )
    assert response.status_code == 200
    names = {entry["input"]: entry for entry in response.json()["names"]}
    for spelling, supplement_id in spellings.items():
        found = [item["supplement_id"] for item in names[spelling]["supplements"]]
        assert found == [supplement_id], spelling

    # An alias is a whole name. A fragment or a look-alike still resolves to nothing.
    fragments = ["k", "d", "b", "b1", "q10", "juice", "john", "vitamin"]
    response = await client.get(
        "/api/label-statements/lookup", params=[("names", name) for name in fragments]
    )
    assert response.status_code == 200
    for entry in response.json()["names"]:
        assert entry["supplements"] == [] and entry["drug_total"] == 0, entry["input"]


@pytest.mark.anyio("asyncio")
async def test_lookup_alias_points_at_the_same_statements_as_the_full_name(client):
    async def statements(first: str, second: str) -> list:
        response = await client.get(
            "/api/label-statements/lookup", params=[("names", first), ("names", second)]
        )
        payload = response.json()
        # An alias changes which label text is shown, never the assessment.
        assert payload["assessment"] == "not_assessed"
        return [
            (group["supplement_id"], group["drug_id"], [item["statement_id"] for item in group["items"]])
            for group in payload["pairs"]
        ]

    assert await statements("K2", "warfarin") == await statements("vitamin k", "warfarin") != []
    assert (
        await statements("grapefruit juice", "simvastatin")
        == await statements("grapefruit", "simvastatin")
        != []
    )


def test_lookup_aliases_are_normalised_and_name_dictionary_supplements():
    dictionary = Path(__file__).resolve().parents[1] / "data" / "openfda_supplement_statements" / "supplement_terms.json"
    known = {entry["id"] for entry in json.loads(dictionary.read_text(encoding="utf-8"))["entries"]}
    for alias, supplement_id in label_statements.LOOKUP_ALIASES.items():
        assert label_statements._normalise_name(alias) == alias, alias
        assert supplement_id in known, supplement_id
