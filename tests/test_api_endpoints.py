import sys
import os
import pytest
import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.docsearch import DocumentSearchService
import api.risk_api as app_module


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    app_module.COMPOUNDS = {
        "caffeine": {
            "id": "caffeine",
            "name": "Caffeine",
            "synonyms": ["coffee", "tea"],
            "aliases": ["guarana extract"],
            "externalIds": {"pubchem": "2519"},
            "referenceUrls": {
                "pubchem": "https://pubchem.ncbi.nlm.nih.gov/compound/2519",
            },
        },
        "aspirin": {
            "id": "aspirin",
            "name": "Aspirin",
            "synonyms": ["acetylsalicylic acid"],
            "externalIds": {"pubchem": "2244"},
            "referenceUrls": {
                "pubchem": "https://pubchem.ncbi.nlm.nih.gov/compound/2244",
            },
        },
        "st_johns_wort": {
            "id": "st_johns_wort",
            "name": "St. John's Wort",
            "synonyms": ["Hypericum perforatum"],
            "aliases": ["St Johns"],
        },
    }
    app_module.INTERACTIONS = [
        {
            "id": "caf-asp",
            "a": "caffeine",
            "b": "aspirin",
            "bidirectional": True,
            "mechanism": [],
            "severity": "Moderate",
            "evidence": "B",
            "effect": "Increased side effects",
            "action": "Monitor",
            "sources": ["s1"],
        }
    ]
    app_module.SOURCES = {"s1": {"id": "s1", "citation": "Example source"}}
    doc_service = DocumentSearchService.from_texts(
        [
            (
                "playbook",
                "Creatine pairs well with caffeine for acute alertness but may increase sleep disruption. Consider magnesium"
                " at night to offset muscle cramps.",
                "Launch night supplement notes",
            ),
            (
                "faq",
                "Monitor for any gastrointestinal side effects such as bloating when stacking creatine, beta-alanine, and"
                " caffeine before intense sessions.",
                "Stack FAQ",
            ),
        ],
        source_description="tests/knowledge-base",
    )
    app_module.set_doc_search_service(doc_service)
    app_module.build_compound_indexes()
    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


pytestmark = pytest.mark.anyio("asyncio")


async def test_search_success(client):
    resp = await client.get("/api/search", params={"q": "caffeine"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert any(item["id"] == "caffeine" for item in data["results"])


async def test_search_matches_synonym(client):
    resp = await client.get("/api/search", params={"q": "coffee"})
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json().get("results", [])}
    assert "caffeine" in ids


async def test_search_matches_external_id(client):
    resp = await client.get("/api/search", params={"q": "2519"})
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json().get("results", [])}
    assert "caffeine" in ids


async def test_search_matches_alias(client):
    resp = await client.get("/api/search", params={"q": "guarana"})
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json().get("results", [])}
    assert "caffeine" in ids


async def test_search_partial_match(client):
    resp = await client.get("/api/search", params={"q": "caff"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["id"] == "caffeine"


async def test_search_case_insensitive(client):
    resp = await client.get("/api/search", params={"q": "ASPIR"})
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json().get("results", [])}
    assert "aspirin" in ids


async def test_search_handles_special_characters(client):
    resp = await client.get("/api/search", params={"q": "st johns"})
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json().get("results", [])}
    assert "st_johns_wort" in ids


async def test_docs_search_returns_results(client):
    resp = await client.get("/api/docs/search", params={"q": "creatine side effects"})
    assert resp.status_code == 200
    payload = resp.json()
    assert "results" in payload
    assert payload["results"]
    assert payload.get("meta", {}).get("documents_indexed", 0) >= 2
    assert payload.get("meta", {}).get("uses_embeddings") is False


async def test_docs_search_requires_query(client):
    resp = await client.get("/api/docs/search")
    assert resp.status_code == 422


async def test_search_missing_query_param(client):
    resp = await client.get("/api/search")
    assert resp.status_code == 422


async def test_interaction_success(client):
    resp = await client.get("/api/interaction", params={"a": "caffeine", "b": "aspirin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["interaction"]["a"] == "caffeine"
    assert data["interaction"]["b"] == "aspirin"
    assert "risk_score" in data


async def test_interaction_missing_parameter(client):
    resp = await client.get("/api/interaction", params={"a": "caffeine"})
    assert resp.status_code == 422


async def test_interaction_not_found(client):
    resp = await client.get("/api/interaction", params={"a": "caffeine", "b": "unknown"})
    assert resp.status_code == 404


async def test_stack_check_success(client):
    payload = {"compounds": ["caffeine", "aspirin"]}
    resp = await client.post("/api/stack/check", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert any(inter["a"] == "caffeine" and inter["b"] == "aspirin" for inter in data["interactions"])


async def test_stack_check_missing_items(client):
    resp = await client.post("/api/stack/check", json={})
    assert resp.status_code == 422


async def test_compounds_endpoint_includes_external_links(client):
    resp = await client.get("/api/compounds")
    assert resp.status_code == 200
    data = resp.json()
    assert "compounds" in data
    compounds_by_id = {item["id"]: item for item in data["compounds"]}
    assert "caffeine" in compounds_by_id
    caffeine = compounds_by_id["caffeine"]
    assert caffeine["externalIds"] == {"pubchem": "2519"}
    assert caffeine["referenceUrls"]["pubchem"] == "https://pubchem.ncbi.nlm.nih.gov/compound/2519"


async def test_api_with_missing_rules_config(client, tmp_path):
    missing_path = tmp_path / "does_not_exist.yaml"
    try:
        app_module.apply_rules(str(missing_path))
        resp = await client.get("/api/interaction", params={"a": "caffeine", "b": "aspirin"})
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_score" in data
    finally:
        app_module.apply_rules()


async def test_api_with_malformed_rules_config(client, tmp_path):
    bad_path = tmp_path / "rules.yaml"
    bad_path.write_text("mechanisms: [\n", encoding="utf-8")
    try:
        app_module.apply_rules(str(bad_path))
        resp = await client.get("/api/interaction", params={"a": "caffeine", "b": "aspirin"})
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_score" in data
    finally:
        app_module.apply_rules()

