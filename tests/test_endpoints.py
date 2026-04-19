from fastapi.testclient import TestClient

def test_health(app_with_data):
    client = TestClient(app_with_data)
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"

def test_search_and_interaction_and_stack(app_with_data):
    client = TestClient(app_with_data)
    r = client.get("/search", params={"q": "caff"})
    assert r.status_code == 200
    hits = r.json().get("compounds", [])
    assert any(h["id"]=="caffeine" for h in hits)

    r2 = client.get("/interaction", params={"a":"caffeine","b":"magnesium"})
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2.get("a_id") == "caffeine"
    assert j2.get("b_id") == "magnesium"

    r3 = client.post("/stack/check", json={"items":["creatine","caffeine","magnesium"]})
    assert r3.status_code == 200
    j3 = r3.json()
    assert j3.get("items") == ["creatine","caffeine","magnesium"]
    assert "matrix" in j3 and "cells" in j3
