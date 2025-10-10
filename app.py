from collections import defaultdict
from fastapi import FastAPI, HTTPException, Query, APIRouter, Request
from fastapi.responses import ORJSONResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, conlist, root_validator, validator
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import yaml, os

# Fuzzy search deps
from rapidfuzz import process, fuzz
from unidecode import unidecode

# Production middleware / observability
from asgi_correlation_id import CorrelationIdMiddleware, correlation_id
from prometheus_fastapi_instrumentator import Instrumentator
import logging

# Synonyms helper
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

app = FastAPI(title="Supplement Interaction API", version="0.2.2", default_response_class=ORJSONResponse)

# Create API router which will host all our application endpoints
api_router = APIRouter(prefix="/api")

# CORS (allow from env or default to all)
origins = os.environ.get("CORS_ALLOWED_ORIGINS", "*")
if origins == "*":
    allow_list = ["*"]
else:
    allow_list = [o.strip() for o in origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Correlation ID middleware
app.add_middleware(CorrelationIdMiddleware)

# Basic structured logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("supptracker")

# Prometheus instrumentation
instrumentator = Instrumentator().instrument(app).expose(app)

@api_router.get("/health")
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
    # Use parse_synonyms for consistent parsing across modules
    try:
        if pd.isna(s):
            return []
    except Exception:
        pass
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


def _normalize_for_search(s: str) -> str:
    """Normalize a string for fuzzy searching: remove diacritics, lowercase and collapse whitespace."""
    if s is None:
        return ""
    return " ".join(unidecode(str(s)).lower().split())


# Build in-memory search index for compounds at startup
# choices: mapping id -> search key (name + synonyms)
_SEARCH_CHOICES: Dict[str, str] = {}
for c in COMPOUNDS:
    parts = [c.get("name", "")]
    parts.extend(c.get("synonyms") or [])
    joined = " ".join(parts)
    _SEARCH_CHOICES[c["id"]] = _normalize_for_search(joined)


# Logging middleware to capture structured request logs
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # try to obtain correlation id from middleware or headers
    try:
        cid_val = correlation_id.get()
    except Exception:
        try:
            cid_val = correlation_id.get_correlation_id()
        except Exception:
            cid_val = request.headers.get("X-Correlation-ID", "")

    logger.info("request_start", extra={"method": request.method, "path": str(request.url.path), "correlation_id": cid_val})
    response = await call_next(request)
    logger.info("request_end", extra={"status_code": response.status_code, "method": request.method, "path": str(request.url.path), "correlation_id": cid_val})
    return response


# Readiness endpoint
@app.get("/ready")
def ready():
    return {"status": "ready"}



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
    items: conlist(str, min_items=2)

    @root_validator(pre=True)
    def alias_items(cls, values: Dict[str, Any]):
        if "items" not in values and "compounds" in values:
            values["items"] = values.pop("compounds")
        return values

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

def search_compounds_fuzzy(q: str, limit: int = 20, threshold: int = 60):
    """Perform fuzzy fuzzy search using RapidFuzz. Returns list of matches with scores."""
    if not q or not q.strip():
        return []
    qn = _normalize_for_search(q)

    # First try exact or prefix matches to boost relevance
    exact = []
    prefix = []
    for c in COMPOUNDS:
        name_norm = _normalize_for_search(c.get("name", ""))
        if name_norm == qn:
            exact.append({"id": c["id"], "name": c["name"], "synonyms": c["synonyms"], "score": 100, "match_type": "exact"})
        elif name_norm.startswith(qn) or any(_normalize_for_search(s).startswith(qn) for s in c.get("synonyms", [])):
            prefix.append({"id": c["id"], "name": c["name"], "synonyms": c["synonyms"], "score": 85, "match_type": "prefix"})

    if len(exact) >= limit:
        return exact[:limit]

    # Use RapidFuzz to score remaining candidates
    choices_map = _SEARCH_CHOICES
    # process.extract returns tuples of (choice, score, key)
    results = process.extract(qn, choices_map, scorer=fuzz.token_set_ratio, limit=limit)

    out = []
    seen = set()
    for match_text, score, cid in results:
        if score < threshold:
            continue
        if cid in seen:
            continue
        seen.add(cid)
        comp = next((x for x in COMPOUNDS if x["id"] == cid), None)
        if not comp:
            continue
        out.append({"id": cid, "name": comp["name"], "synonyms": comp["synonyms"], "score": int(score), "match_type": "fuzzy"})

    # Merge exact/prefix results first
    merged = exact + prefix
    # dedupe merged ids
    final = merged + [r for r in out if r["id"] not in {m["id"] for m in merged}]
    return final[:limit]


@api_router.get("/search")
def search(q: str = Query(..., description="Compound name or synonym"), limit: int = Query(20, ge=1, le=100)):
    results = search_compounds_fuzzy(q, limit=limit)
    return {"compounds": results}

@api_router.get("/interaction")
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

@api_router.post("/stack/check")
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


# Mount API router
app.include_router(api_router)
