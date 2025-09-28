import sys
import os
import pytest
import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.risk_api as app_module


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    app_module.COMPOUNDS = {
        "caffeine": {"id": "caffeine", "name": "Caffeine", "synonyms": ["coffee", "tea"]},
        "aspirin": {"id": "aspirin", "name": "Aspirin", "synonyms": ["acetylsalicylic acid"]},
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

