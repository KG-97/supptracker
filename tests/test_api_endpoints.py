import sys
import os
import pytest
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.risk_api as app_module


@pytest.fixture
def client():
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
    return TestClient(app_module.app)


def test_search_success(client):
    resp = client.get("/api/search", params={"q": "caffeine"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert any(item["id"] == "caffeine" for item in data["results"])


def test_search_missing_query_param(client):
    resp = client.get("/api/search")
    assert resp.status_code == 422


def test_interaction_success(client):
    resp = client.get("/api/interaction", params={"a": "caffeine", "b": "aspirin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["interaction"]["a"] == "caffeine"
    assert data["interaction"]["b"] == "aspirin"
    assert "risk_score" in data


def test_interaction_missing_parameter(client):
    resp = client.get("/api/interaction", params={"a": "caffeine"})
    assert resp.status_code == 422


def test_interaction_not_found(client):
    resp = client.get("/api/interaction", params={"a": "caffeine", "b": "unknown"})
    assert resp.status_code == 404


def test_stack_check_success(client):
    payload = {"compounds": ["caffeine", "aspirin"]}
    resp = client.post("/api/stack/check", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert any(inter["a"] == "caffeine" and inter["b"] == "aspirin" for inter in data["interactions"])


def test_stack_check_missing_items(client):
    resp = client.post("/api/stack/check", json={})
    assert resp.status_code == 422

