from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import pandas as pd
import yaml, os

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")

def load_csv(name: str) -> pd.DataFrame:
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        raise FileNotFoundError(f"Missing data file: {name}")
    return pd.read_csv(p)

def load_yaml(name: str) -> dict:
    p = os.path.join(DATA, name)
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

app = FastAPI(title="Supplement Interaction API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    """Lightweight health endpoint for probes."""
    return {"status": "ok", "service": "supptracker-backend", "version": app.version}


@app.get("/info")
def info():
    """Service info: version and basic environment details."""
    commit = os.environ.get("GIT_COMMIT", None)
    return {"service": "supptracker-backend", "version": app.version, "commit": commit}

COMPOUNDS_DF = load_csv("compounds.csv")
INTERACTIONS_DF = load_csv("interactions.csv")
SOURCES_DF = load_csv("sources.csv")
RULES = load_yaml("risk_rules.yaml")

def to_synonyms(s: str):
    if pd.isna(s) or s.strip() == "":
        return []
    return [x.strip() for x in str(s).split(";")]

COMPOUNDS = []
for _, row in COMPOUNDS_DF.iterrows():
    COMPOUNDS.append({
        "id": row["id"],
        "name": row["name"],
        "synonyms": to_synonyms(row.get("synonyms","")),
        "class": row.get("class",""),
        "route": row.get("route",""),
        "common_dose": row.get("common_dose",""),
        "qt_risk": row.get("qt_risk",""),
        "notes": row.get("notes",""),
    })

INTERACTIONS = INTERACTIONS_DF.to_dict(orient="records")
SOURCES = {row["id"]: row for _, row in SOURCES_DF.iterrows()}

sev_map = RULES.get("severity_map", {"None":0,"Mild":1,"Moderate":2,"Severe":3})
evd_map = RULES.get("evidence_grade_map", {"A":1,"B":2,"C":3,"D":4})
weights = RULES.get("weights", {"w_sev":0.9,"w_evd":0.4,"w_mech":0.2,"w_dose":0.3,"w_user":0.3})
buckets = RULES.get("buckets", {
    "low": {"max":0.7,"label":"No meaningful interaction","action":"No meaningful interaction"},
    "caution":{"min":0.71,"max":1.5,"label":"Caution","action":"Monitor"},
    "high":{"min":1.51,"label":"High","action":"Avoid"}
})

def compute_score(interaction: Dict[str,Any], doses: Optional[str]=None, flags: Optional[str]=None):
    sev = sev_map.get(str(interaction.get("severity","None")), 0)
    evd = evd_map.get(str(interaction.get("evidence_grade","D")), 4)
    mech_tags = str(interaction.get("mechanism_tags","")).split(";") if interaction.get("mechanism_tags") else []
    mech_boost = 0.05 * len([m for m in mech_tags if m.strip()])
    dose_factor = 0.1 if doses else 0.0
    user_factor = 0.1 * len([f for f in (flags or "").split(",") if f.strip()]) if flags else 0.0
    score = (weights.get("w_sev",0.9) * sev
             + weights.get("w_evd",0.4) * (1.0/evd if evd>0 else 1.0)
             + weights.get("w_mech",0.2) * mech_boost
             + weights.get("w_dose",0.3) * dose_factor
             + weights.get("w_user",0.3) * user_factor)
    low_max = buckets["low"]["max"]
    high_min = buckets["high"]["min"]
    if score <= low_max:
        bucket_label = buckets["low"]["label"]; action = buckets["low"]["action"]
    elif score >= high_min:
        bucket_label = buckets["high"]["label"]; action = buckets["high"]["action"]
    else:
        bucket_label = buckets["caution"]["label"]; action = interaction.get("action", buckets["caution"]["action"])
    return round(float(score), 3), bucket_label, action

def find_interaction(a: str, b: str):
    a, b = a.strip().lower(), b.strip().lower()
    for row in INTERACTIONS:
        ca = str(row["compound_a"]).lower()
        cb = str(row["compound_b"]).lower()
        if (ca == a and cb == b) or (ca == b and cb == a):
            return row
    return None

def search_compounds(q: str):
    # Support simple prefix matching and return up to 20 results
    ql = (q or "").strip().lower()
    if ql == "":
        return []
    hits = []
    for c in COMPOUNDS:
        if c["id"] and c["id"].lower().startswith(ql):
            hits.append({"id": c["id"], "name": c["name"], "synonyms": c["synonyms"]})
            continue
        if ql in c["name"].lower() or any(ql in s.lower() for s in c["synonyms"]):
            hits.append({"id": c["id"], "name": c["name"], "synonyms": c["synonyms"]})
    hits.sort(key=lambda x: len(x["name"]))
    return hits[:20]

@app.get("/search")
def search(q: str = Query(..., description="Compound name or synonym"), page: int = 1, per_page: int = 20):
    """Search compounds with paging. Returns total and page of results."""
    all_hits = search_compounds(q)
    per_page = max(1, min(100, per_page))
    page = max(1, page)
    start = (page - 1) * per_page
    end = start + per_page
    return {"total": len(all_hits), "page": page, "per_page": per_page, "compounds": all_hits[start:end]}

@app.get("/interaction")
def interaction(a: str, b: str, flags: Optional[str] = None, doses: Optional[str] = None):
    if not a or not b:
        raise HTTPException(status_code=400, detail="Both 'a' and 'b' must be provided")
    # normalize inputs (allow IDs or names)
    a_n = str(a).strip().lower()
    b_n = str(b).strip().lower()
    inter = find_interaction(a_n, b_n)
    if not inter:
        # try swapping or searching by name/id mapping
        inter = find_interaction(b_n, a_n)
    if not inter:
        raise HTTPException(status_code=404, detail=f"No interaction found for pair: {a}/{b}")
    score, bucket, action = compute_score(inter, doses=doses, flags=flags)
    src_ids = []
    if inter.get("source_ids"):
        src_ids = [s.strip() for s in str(inter["source_ids"]).split(";") if s.strip()]
    sources = [SOURCES[s] for s in src_ids if s in SOURCES]
    return {
        "pair": {"a": a, "b": b},
        "interaction": {
            **inter,
            "score": score,
            "bucket": bucket,
            "action_resolved": action,
            "sources": sources
        }
    }

@app.post("/stack/check")
def stack_check(payload: Dict[str, Any]):
    items = payload.get("items", [])
    if not isinstance(items, list) or len(items) == 0:
        raise HTTPException(status_code=400, detail="items must be a non-empty list")
    n = len(items)
    matrix = [[None for _ in range(n)] for __ in range(n)]
    cells = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a, b = items[i], items[j]
            inter = find_interaction(a, b)
            if inter:
                score, bucket, action = compute_score(inter, doses=None, flags=None)
                matrix[i][j] = score
                # include resolved interaction details to help clients render stacks
                src_ids = [s.strip() for s in str(inter.get("source_ids", "")).split(";") if s.strip()]
                sources_list = [SOURCES[s] for s in src_ids if s in SOURCES]
                cells.append({
                    "a": a,
                    "b": b,
                    "score": score,
                    "bucket": bucket,
                    "action": action,
                    "interaction_id": inter.get("id"),
                    "mechanism_tags": inter.get("mechanism_tags"),
                    "sources": sources_list,
                })
            else:
                matrix[i][j] = None
    return {"items": items, "matrix": matrix, "cells": cells}
