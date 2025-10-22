from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import os

import pandas as pd
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, conlist, validator

from backend.synonyms import parse_synonyms

# Allow tests (or deployments) to override the default data directory via an
# environment variable.  In normal operation the CSV/YAML data files live in the
# repository's ``data`` directory.  During testing we want to use lightweight
# fixtures instead, so the path can be pointed elsewhere by setting
# ``SUPPTRACKER_DATA`` before importing this module.
HERE = os.path.dirname(__file__)
DATA = os.environ.get("SUPPTRACKER_DATA", os.path.join(HERE, "data"))

def load_csv(name: str) -> pd.DataFrame:
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        raise FileNotFoundError(f"Missing data file: {name}")
    return pd.read_csv(p)

def load_yaml(name: str) -> dict:
    p = os.path.join(DATA, name)
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

app = FastAPI(title="Supplement Interaction API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    """Lightweight health endpoint for probes."""
    return {"status": "ok", "service": "supptracker-backend", "version": app.version}

COMPOUNDS_DF = load_csv("compounds.csv")
INTERACTIONS_DF = load_csv("interactions.csv")
# Normalise column names so downstream code can rely on a consistent schema
INTERACTIONS_DF = INTERACTIONS_DF.rename(
    columns={
        "a": "compound_a",
        "b": "compound_b",
        "mechanism": "mechanism_tags",
        "evidence": "evidence_grade",
        "sources": "source_ids",
    }
)
SOURCES_DF = load_csv("sources.csv")
RULES = load_yaml("risk_rules.yaml")

def to_synonyms(s: str):
    if pd.isna(s) or str(s).strip() == "":
        return []
    return parse_synonyms(s)

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

def _normalise_compound(value: Any) -> str:
    return str(value).strip().lower()


def _interaction_key(a: Any, b: Any) -> Tuple[str, str]:
    return tuple(sorted((_normalise_compound(a), _normalise_compound(b))))


INTERACTIONS: List[Dict[str, Any]] = []
INTERACTION_INDEX: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
for row in INTERACTIONS_DF.to_dict(orient="records"):
    record = {**row}
    record["bidirectional"] = str(row.get("bidirectional", "")).strip().lower() in {"true", "1", "yes", "y"}
    INTERACTIONS.append(record)
    INTERACTION_INDEX[_interaction_key(record["compound_a"], record["compound_b"])].append(record)

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
    a_norm = _normalise_compound(a)
    b_norm = _normalise_compound(b)
    candidates = INTERACTION_INDEX.get(_interaction_key(a, b), [])
    for row in candidates:
        ca = _normalise_compound(row["compound_a"])
        cb = _normalise_compound(row["compound_b"])
        if ca == a_norm and cb == b_norm:
            return row
        if row.get("bidirectional") and ca == b_norm and cb == a_norm:
            return row
    return None


class StackCheckRequest(BaseModel):
    items: conlist(str, min_items=2) = Field(..., alias="compounds")

    class Config:
        allow_population_by_field_name = True

    @validator("items", pre=True)
    def validate_items(cls, value: Any):
        if not isinstance(value, list):
            raise ValueError("items must be provided as a list of compounds")
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if len(cleaned) < 2:
            raise ValueError("items must include at least two compounds")
        return cleaned

def search_compounds(q: str):
    ql = q.lower()
    hits = []
    for c in COMPOUNDS:
        if ql in c["id"].lower() or ql in c["name"].lower() or any(ql in s.lower() for s in c["synonyms"]):
            hits.append({"id": c["id"], "name": c["name"], "synonyms": c["synonyms"]})
    hits.sort(key=lambda x: len(x["name"]))
    return hits[:20]

@app.get("/api/search")
def search(q: str = Query(..., description="Compound name or synonym")):
    return {"compounds": search_compounds(q)}

@app.get("/api/interaction")
def interaction(a: str, b: str, flags: Optional[str] = None, doses: Optional[str] = None):
    inter = find_interaction(a, b)
    if not inter:
        raise HTTPException(status_code=404, detail="No interaction found for pair")
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

@app.post("/api/stack/check")
def stack_check(payload: StackCheckRequest):
    items = payload.items
    n = len(items)
    matrix = [[None for _ in range(n)] for __ in range(n)]
    interactions: List[Dict[str, Any]] = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = items[i], items[j]
            inter = find_interaction(a, b)
            if not inter:
                continue
            score, bucket, action = compute_score(inter, doses=None, flags=None)
            matrix[i][j] = score
            matrix[j][i] = score
            entry = {
                "a": a,
                "b": b,
                "severity": inter.get("severity"),
                "evidence": inter.get("evidence_grade"),
                "effect": inter.get("effect"),
                "action": inter.get("action"),
                "action_resolved": action,
                "bucket": bucket,
                "score": score,
                "risk_score": score,
            }
            interactions.append(entry)
    return {"items": items, "matrix": matrix, "cells": interactions, "interactions": interactions}
