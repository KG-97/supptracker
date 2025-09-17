import os
import sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient
from app import app, COMPOUNDS

client = TestClient(app)


def test_health_and_info():
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"

    r2 = client.get("/info")
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2.get("service") == "supptracker-backend"


def test_search_endpoint():
    # pick a likely compound term from fixtures (caffeine expected in data)
    r = client.get("/search", params={"q": "caffeine"})
    assert r.status_code == 200
    j = r.json()
    assert "compounds" in j and "total" in j


def test_interaction_not_found():
    r = client.get("/interaction", params={"a": "nonexistent-xyz", "b": "other-abc"})
    assert r.status_code == 404


def test_stack_check_bad_payload():
    r = client.post("/stack/check", json={})
    assert r.status_code == 400


def test_stack_check_positive_if_available():
    if len(COMPOUNDS) < 2:
        pytest.skip("Not enough compounds for integration stack test")
    items = [COMPOUNDS[0]["id"], COMPOUNDS[1]["id"]]
    r = client.post("/stack/check", json={"items": items})
    assert r.status_code == 200
    j = r.json()
    assert "items" in j and "matrix" in j and "cells" in j
    assert isinstance(j["cells"], list)
