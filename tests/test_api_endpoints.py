import sys
import os
import pytest
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as app_module


@pytest.fixture
def client():
    app_module.COMPOUNDS = [
        {"id": "caffeine", "name": "Caffeine", "synonyms": ["coffee", "tea"]},
        {"id": "aspirin", "name": "Aspirin", "synonyms": ["acetylsalicylic acid"]},
    ]
    app_module.INTERACTIONS = [
        {
            "compound_a": "caffeine",
            "compound_b": "aspirin",
            "severity": "Moderate",
            "evidence_grade": "B",
            "mechanism_tags": "",
            "source_ids": "source1",
            "action": "Monitor",
        }
    ]
    app_module.SOURCES = {"source1": {"id": "source1", "title": "Example source"}}
    return TestClient(app_module.app)


def test_search_success(client):
    resp = client.get("/search", params={"q": "caffeine"})
    assert resp.status_code == 200
    data = resp.json()
    assert "compounds" in data
    assert isinstance(data["compounds"], list)
    assert any(item["id"] == "caffeine" for item in data["compounds"])


def test_search_missing_query_param(client):
    resp = client.get("/search")
    assert resp.status_code == 422


def test_interaction_success(client):
    resp = client.get("/interaction", params={"a": "caffeine", "b": "aspirin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["pair"] == {"a": "caffeine", "b": "aspirin"}
    assert "interaction" in data
    assert "score" in data["interaction"]


def test_interaction_missing_parameter(client):
    resp = client.get("/interaction", params={"a": "caffeine"})
    assert resp.status_code == 422


def test_interaction_not_found(client):
    resp = client.get("/interaction", params={"a": "caffeine", "b": "unknown"})
    assert resp.status_code == 404


def test_stack_check_success(client):
    payload = {"items": ["caffeine", "aspirin"]}
    resp = client.post("/stack/check", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == payload["items"]
    assert "matrix" in data and isinstance(data["matrix"], list)
    assert len(data["matrix"]) == len(payload["items"])


def test_stack_check_missing_items(client):
    resp = client.post("/stack/check", json={})
    assert resp.status_code == 400


def test_stack_check_invalid_items(client):
    resp = client.post("/stack/check", json={"items": []})
    assert resp.status_code == 400
    resp = client.post("/stack/check", json={"items": "caffeine"})
    assert resp.status_code == 400
