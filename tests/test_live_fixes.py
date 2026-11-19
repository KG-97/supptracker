"""Fixes from the live test of 18 Nov 2026: names people type, stack reporting, hardening."""

import logging
from pathlib import Path

import httpx
import pytest

import api.label_statements as label_statements
import api.risk_api as risk_api

DATASET_DIR = Path(__file__).resolve().parents[1] / "data" / "openfda_supplement_statements"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=risk_api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture(autouse=True)
def statement_dataset():
    label_statements.reload_label_statements(DATASET_DIR)
    yield
    label_statements.reload_label_statements(DATASET_DIR)


@pytest.fixture
def salt_compounds(monkeypatch):
    # Self-contained: other tests may have loaded the real dataset, which has a plain "sertraline" id.
    compounds = {}
    compounds["sertraline-hydrochloride"] = {"id": "sertraline-hydrochloride", "name": "SERTRALINE HYDROCHLORIDE"}
    compounds["warfarin-sodium"] = {"id": "warfarin-sodium", "name": "WARFARIN SODIUM"}
    compounds["metoprolol-tartrate"] = {"id": "metoprolol-tartrate", "name": "METOPROLOL TARTRATE"}
    compounds["metoprolol-succinate"] = {"id": "metoprolol-succinate", "name": "METOPROLOL SUCCINATE"}
    monkeypatch.setattr(risk_api, "COMPOUNDS", compounds)
    yield compounds


def test_base_name_resolves_to_the_single_salt_form(salt_compounds):
    assert risk_api.resolve_compound("sertraline") == "sertraline-hydrochloride"
    assert risk_api.resolve_compound("Warfarin") == "warfarin-sodium"
    salt_compounds["fluoxetine-hcl"] = {"id": "fluoxetine-hcl", "name": "FLUOXETINE HCL"}
    assert risk_api.resolve_compound("fluoxetine") == "fluoxetine-hcl"


def test_ambiguous_base_name_resolves_to_nothing(salt_compounds):
    assert risk_api.resolve_compound("metoprolol") is None


def test_different_compounds_sharing_a_label_key_are_not_duplicates():
    # Antigravity review 2026-11-19: two amlodipine combination products share one label key.
    shared = ((), ("amlodipine",))
    key = risk_api._item_key
    assert key("amlodipine-and-atorvastatin", shared) != key("amlodipine-and-benazepril", shared)
    assert key("warfarin-sodium", None) == key("warfarin-sodium", shared)
    assert key(None, (("st-johns-wort",), ())) == key(None, (("st-johns-wort",), ()))
    assert key("sertraline-hydrochloride", shared) != key(None, shared)


@pytest.mark.anyio("asyncio")
async def test_stack_keeps_distinct_combination_products(client, monkeypatch, salt_compounds):
    salt_compounds["amlodipine-and-atorvastatin"] = {"id": "amlodipine-and-atorvastatin", "name": "AMLODIPINE AND ATORVASTATIN"}
    salt_compounds["amlodipine-and-benazepril"] = {"id": "amlodipine-and-benazepril", "name": "AMLODIPINE AND BENAZEPRIL"}
    monkeypatch.setattr(label_statements, "recognised_name_key", lambda name: ((), ("amlodipine",)) if "amlodipine" in name.lower() else None)
    response = await client.post("/api/stack/check", json={"compounds": ["amlodipine and atorvastatin", "amlodipine and benazepril"]})
    body = response.json()
    assert body["duplicates_removed"] == []
    assert body["evaluated_items"] == ["amlodipine and atorvastatin", "amlodipine and benazepril"]


@pytest.mark.anyio("asyncio")
async def test_label_supplement_with_drug_is_not_assessed_not_404(client, salt_compounds):
    response = await client.get("/api/interaction", params={"a": "St John's wort", "b": "sertraline"})
    assert response.status_code == 200
    body = response.json()
    assert body["assessment"] == "not_assessed"
    assert body["interaction"] is None and body["risk_score"] is None
    assert body["pair"] == {"a": None, "b": "sertraline-hydrochloride"}
    assert [item["recognised_by"] for item in body["names"]] == ["label_statements", "compound"]


@pytest.mark.anyio("asyncio")
async def test_unrecognised_name_is_404_and_named(client):
    response = await client.get("/api/interaction", params={"a": "magnesum", "b": "caffeine"})
    assert response.status_code == 404
    assert "magnesum" in response.json()["detail"]


def test_stack_reports_every_unknown_and_evaluates_the_rest(salt_compounds):
    result = risk_api.check_stack(
        risk_api.StackRequest(compounds=["Melatonin", "Magnesum", "WARFARIN SODIUM", "warfarin sodium", "zinc", "Qwertyx"])
    )
    assert result["unrecognised"] == ["Magnesum", "Qwertyx"]
    assert result["duplicates_removed"] == ["warfarin sodium"]
    assert result["evaluated_items"] == ["Melatonin", "WARFARIN SODIUM", "zinc"]
    assert result["coverage"]["total_pairs"] == 3
    assert result["assessment"] == "not_assessed"
    assert "does not mean the combination is safe" in result["message"]


@pytest.mark.anyio("asyncio")
async def test_metrics_hidden_by_default(client, monkeypatch):
    monkeypatch.delenv("SUPPTRACKER_METRICS", raising=False)
    response = await client.get("/metrics")
    assert response.status_code == 404


@pytest.mark.anyio("asyncio")
async def test_security_headers_and_hsts_only_over_https(client):
    plain = await client.get("/api/health")
    for header in ("content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy"):
        assert header in plain.headers
    assert "frame-ancestors 'none'" in plain.headers["content-security-policy"]
    assert "strict-transport-security" not in plain.headers
    secure = await client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert secure.headers["strict-transport-security"].startswith("max-age=")


@pytest.mark.anyio("asyncio")
async def test_long_search_query_is_rejected(client):
    assert (await client.get("/api/search", params={"q": "x" * 101})).status_code == 422
    assert (await client.get("/api/label-statements", params={"q": "x" * 101})).status_code == 422
    assert (await client.get("/api/search", params={"q": "x" * 100})).status_code == 200


@pytest.mark.anyio("asyncio")
async def test_label_count_is_an_integer(client):
    body = (await client.get("/api/label-statements", params={"limit": 3})).json()
    assert body["items"] and all(isinstance(item["label_count"], int) for item in body["items"])


def test_base_fallback_rejects_salts_and_ambiguous_prefixes(salt_compounds):
    salt_compounds.update({
        "sodium-other": {"id": "sodium-other", "name": "SODIUM BICARBONATE"},
        "magnesium-citrate": {"id": "magnesium-citrate", "name": "MAGNESIUM CITRATE"},
        "magnesium-oxide": {"id": "magnesium-oxide", "name": "MAGNESIUM OXIDE"},
    })
    assert risk_api.resolve_compound("warfarin potassium") is None
    assert risk_api.resolve_compound("sodium chloride") is None
    assert risk_api.resolve_compound("magnesium") is None
    assert risk_api.resolve_compound("---") is None
    assert risk_api.resolve_compound("sertraline") == "sertraline-hydrochloride"


@pytest.mark.anyio("asyncio")
async def test_label_aliases_cannot_be_paired_with_themselves(client, salt_compounds):
    response = await client.get(
        "/api/interaction",
        params={"a": "St. John's Wort", "b": "St John's wort"},
    )
    assert response.status_code == 422


def test_stack_deduplicates_label_aliases(salt_compounds):
    result = risk_api.check_stack(
        risk_api.StackRequest(compounds=["St. John's Wort", "St John's wort"])
    )
    assert result["evaluated_items"] == ["St. John's Wort"]
    assert result["duplicates_removed"] == ["St John's wort"]


def test_unknown_makes_otherwise_assessed_stack_partial(monkeypatch):
    compounds = {
        "caffeine": {"id": "caffeine", "name": "caffeine"},
        "aspirin": {"id": "aspirin", "name": "aspirin"},
    }
    monkeypatch.setattr(risk_api, "COMPOUNDS", compounds)
    monkeypatch.setattr(risk_api, "_ensure_interaction_lookup", lambda: None)
    monkeypatch.setattr(
        risk_api, "_INTERACTION_LOOKUP",
        {("caffeine", "aspirin"): {"severity": "moderate", "evidence": "A"}},
    )
    monkeypatch.setattr(risk_api, "compute_risk", lambda interaction: 2.0)
    result = risk_api.check_stack(
        risk_api.StackRequest(compounds=["caffeine", "aspirin", "magnesum"])
    )
    assert result["coverage"]["assessed_pairs"] == 1
    assert result["assessment"] == "partial"
    assert "does not mean the combination is safe" in result["message"]


@pytest.mark.anyio("asyncio")
async def test_long_pair_and_stack_values_are_not_reflected(client):
    long_value = "x" * 101
    pair = await client.get(
        "/api/interaction", params={"a": long_value, "b": "caffeine"}
    )
    stack = await client.post(
        "/api/stack/check", json={"compounds": ["caffeine", long_value]}
    )
    assert pair.status_code == stack.status_code == 422
    assert long_value not in pair.text
    assert long_value not in stack.text


@pytest.mark.anyio("asyncio")
async def test_metrics_trailing_slash_is_hidden(client, monkeypatch):
    monkeypatch.delenv("SUPPTRACKER_METRICS", raising=False)
    assert (await client.get("/metrics/")).status_code == 404


@pytest.mark.anyio("asyncio")
async def test_search_includes_label_supplement(client):
    body = (await client.get("/api/search", params={"q": "melatonin"})).json()
    assert any(item["name"] == "Melatonin" and item["kind"] == "supplement"
               for item in body["label_names"])


@pytest.mark.anyio("asyncio")
async def test_pair_suggests_magnesium(client):
    response = await client.get("/api/interaction", params={"a": "magnesum", "b": "caffeine"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Not recognised: magnesum"
    assert "Magnesium" in response.json()["suggestions"]["magnesum"]


@pytest.mark.anyio("asyncio")
async def test_stack_suggests_magnesium(client):
    response = await client.post("/api/stack/check", json={"compounds": ["magnesum", "caffeine"]})
    assert response.status_code == 200
    body = response.json()
    assert body["unrecognised"] == ["magnesum"]
    assert "Magnesium" in body["suggestions"]["magnesum"]


@pytest.mark.anyio("asyncio")
async def test_search_suggests_magnesium(client):
    response = await client.get("/api/search", params={"q": "magnesum"})
    body = response.json()
    assert body["results"] == [] and body["label_names"] == []
    assert "Magnesium" in body["suggestions"]["magnesum"]


@pytest.mark.anyio("asyncio")
async def test_search_label_names_agree_with_the_lookup(client):
    # Antigravity review 2: a substring hit here hid "No compounds matched" while the note under the box,
    # which uses the lookup, showed nothing.
    partial = (await client.get("/api/search", params={"q": "magnesi"})).json()
    assert partial["label_names"] == []
    whole = (await client.get("/api/search", params={"q": "melatonin"})).json()
    assert [item["id"] for item in whole["label_names"] if item["kind"] == "supplement"] == ["melatonin"]


@pytest.fixture
def base_compounds(monkeypatch):
    # The assessed dataset (data/compounds.csv) names drugs by their base: "Warfarin", "Levothyroxine".
    compounds = {
        "warfarin": {"id": "warfarin", "name": "Warfarin", "synonyms": ["coumadin"]},
        "levothyroxine": {"id": "levothyroxine", "name": "Levothyroxine"},
        "calcium": {"id": "calcium", "name": "Calcium"},
        "fish-oil": {"id": "fish-oil", "name": "Fish Oil (Omega-3)", "synonyms": ["fish oil"]},
    }
    monkeypatch.setattr(risk_api, "COMPOUNDS", compounds)
    yield compounds


def test_label_salt_spelling_resolves_to_the_base_compound(base_compounds):
    # Cloud review 2026-11-19: "levothyroxine sodium" fell through to the label-only path and was reported
    # as having no assessed record, though "Levothyroxine" has one.
    assert risk_api.resolve_compound("warfarin sodium") == "warfarin"
    assert risk_api.resolve_compound("LEVOTHYROXINE SODIUM") == "levothyroxine"
    assert risk_api.resolve_compound("coumadin sodium") == "warfarin"
    assert risk_api.resolve_compound("calcium") == "calcium"
    assert risk_api.resolve_compound("calcium magnesium") is None  # the base is itself a salt word
    assert risk_api.resolve_compound("sodium chloride") is None
    assert risk_api.resolve_compound("warfarin sodium tablets") is None  # salt words only at the end


@pytest.mark.anyio("asyncio")
async def test_salt_spelling_reaches_the_assessed_record(client, monkeypatch, base_compounds):
    monkeypatch.setattr(risk_api, "_ensure_interaction_lookup", lambda: None)
    monkeypatch.setattr(
        risk_api, "_INTERACTION_LOOKUP",
        {("calcium", "levothyroxine"): {"severity": "Moderate", "evidence": "B", "sources": []}},
    )
    monkeypatch.setattr(risk_api, "compute_risk", lambda interaction: 2.0)
    body = (await client.get("/api/interaction", params={"a": "levothyroxine sodium", "b": "calcium"})).json()
    assert body["assessment"] == "assessed"
    assert body["pair"] == {"a": "levothyroxine", "b": "calcium"}


def test_stack_treats_a_salt_spelling_as_its_base_compound(base_compounds):
    result = risk_api.check_stack(risk_api.StackRequest(compounds=["Warfarin", "warfarin sodium", "fish oil"]))
    assert result["duplicates_removed"] == ["warfarin sodium"]
    assert result["evaluated_items"] == ["Warfarin", "fish oil"]


def test_only_a_real_ambiguity_is_logged(base_compounds, salt_compounds, caplog):
    # Cloud review 2026-11-19: "fish" matches one compound and is rejected; that is not an ambiguity.
    salt_compounds.update(base_compounds)
    with caplog.at_level(logging.WARNING, logger=risk_api.logger.name):
        assert risk_api.resolve_compound("fish") is None
    assert "Ambiguous" not in caplog.text
    with caplog.at_level(logging.WARNING, logger=risk_api.logger.name):
        assert risk_api.resolve_compound("metoprolol") is None
    assert "Ambiguous compound base name 'metoprolol'" in caplog.text
