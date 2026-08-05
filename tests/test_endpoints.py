import importlib
from fastapi.testclient import TestClient

def test_health():
    import app as backend
    client = TestClient(backend.app)
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"

def test_search_and_interaction_and_stack():
    import app as backend
    client = TestClient(backend.app)
    r = client.get("/api/search", params={"q": "caff"})
    assert r.status_code == 200
    hits = r.json().get("compounds", [])
    assert any(h["id"]=="caffeine" for h in hits)

    r2 = client.get("/api/interaction", params={"a":"caffeine","b":"magnesium"})
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["pair"]["a"] == "caffeine"
    assert j2["pair"]["b"] == "magnesium"
    assert j2["found"] is True

    r3 = client.post("/api/stack/check", json={"items":["creatine","caffeine","magnesium"]})
    assert r3.status_code == 200
    j3 = r3.json()
    assert j3.get("items") == ["creatine","caffeine","magnesium"]
    assert "matrix" in j3 and "cells" in j3
