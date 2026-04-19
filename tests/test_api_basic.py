import os, json, pandas as pd, yaml
from fastapi.testclient import TestClient
import importlib

def make_temp_data(tmp):
    d = tmp
    pd.DataFrame([
        {"id":"caffeine","name":"Caffeine","synonyms":"1,3,7-trimethylxanthine|trimethylxanthine"},
        {"id":"magnesium","name":"Magnesium","synonyms":"Mg; magnesium / Mag"}
    ]).to_csv(d/"compounds.csv", index=False)
    pd.DataFrame([
        {"compound_a":"caffeine","compound_b":"magnesium","severity":"Mild","evidence_grade":"B","mechanism_tags":"CNS;diuresis","source_ids":"s1"}
    ]).to_csv(d/"interactions.csv", index=False)
    pd.DataFrame([
        {"id":"s1","title":"Some Study","citation":"J Imaginary 2020"}
    ]).to_csv(d/"sources.csv", index=False)
    yaml.safe_dump({
        "weights":{"w_sev":0.9,"w_evd":0.4,"w_mech":0.2,"w_dose":0.3,"w_user":0.3},
        "buckets":{
            "low":{"max":0.7,"label":"No meaningful interaction","action":"No meaningful interaction"},
            "caution":{"min":0.71,"max":1.5,"label":"Caution","action":"Monitor"},
            "high":{"min":1.51,"label":"High","action":"Avoid"}
        }
    }, open(d/"risk_rules.yaml","w"))

def test_api_endpoints(tmp_path, monkeypatch):
    make_temp_data(tmp_path)
    monkeypatch.setenv("SUPPTRACKER_DATA_DIR", str(tmp_path))

    import app as backend
    importlib.reload(backend)

    client = TestClient(backend.app)

    r = client.get("/api/health"); assert r.status_code == 200
    r = client.get("/api/search", params={"q":"trimethyl"}); assert r.status_code == 200
    names = [c["id"] for c in r.json()["compounds"]]
    assert "caffeine" in names

    r = client.get("/api/interaction", params={"a":"caffeine","b":"magnesium"}); assert r.status_code == 200
    body = r.json()
    assert body["interaction"]["score"] >= 0

    r = client.post("/api/stack/check", json={"items":["caffeine","magnesium"]})
    assert r.status_code == 200
    assert r.json()["matrix"][0][1] is not None
