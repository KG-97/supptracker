"""
Main FastAPI application for the Supplement Interaction API.

This module wires together the data loading, scoring logic and HTTP endpoints
exposed via FastAPI. It uses Pydantic models defined in ``models.py`` to
enforce strict schema validation and to generate comprehensive API docs.
The application loads CSV/YAML data at startup and supports overriding
the data directory via the ``SUPPTRACKER_DATA_DIR`` environment variable.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import pandas as pd
import yaml, os
from pathlib import Path
from synonyms import parse_synonyms, normalize_names

# Import models used for request/response validation and OpenAPI generation
from models import (
    SearchResponse,
    InteractionResponse,
    StackCheckRequest,
    StackCheckResponse,
    CompoundHit,
    CompoundDetail,
    CompoundsResponse,
    InteractionPair,
    InteractionDetail,
    InteractionSource,
    StackCell,
)

# Determine the directory where CSV/YAML data files are located. You can set
# the ``SUPPTRACKER_DATA_DIR`` environment variable to override the default
# ``data/`` directory relative to this file.
HERE = Path(__file__).parent
DATA = Path(os.environ.get("SUPPTRACKER_DATA_DIR", HERE / "data"))


def load_csv(name: str) -> pd.DataFrame:
    """Load a CSV file from the configured data directory."""
    p = DATA / name
    if not p.exists():
        raise FileNotFoundError(f"Missing data file: {name} in {DATA}")
    return pd.read_csv(p)


def load_yaml(name: str) -> dict:
    """Load a YAML file from the configured data directory."""
    p = DATA / name
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# Instantiate the FastAPI application
app = FastAPI(
    title="SuppTracker API",
    version="1.0.0",
    description="Supplement interaction scoring and stack analysis API.",
)
api = APIRouter(prefix="/api")

# Enable permissive CORS by default.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.get("/health")
def health() -> Dict[str, str]:
    """Simple health check endpoint used by readiness/liveness probes."""
    return {"status": "ok", "service": "supptracker-backend", "version": app.version}


# ── Data loading ──────────────────────────────────────────────────────────────
try:
    COMPOUNDS_DF = load_csv("compounds.csv")
    INTERACTIONS_DF = load_csv("interactions.csv")
    SOURCES_DF = load_csv("sources.csv")
except Exception as e:
    COMPOUNDS_DF = pd.DataFrame()
    INTERACTIONS_DF = pd.DataFrame()
    SOURCES_DF = pd.DataFrame()
    _BOOT_ERROR = str(e)
else:
    _BOOT_ERROR = ""

# Load risk rules YAML after data is loaded
RULES: dict = {}
if not _BOOT_ERROR:
    try:
        RULES = load_yaml("risk_rules.yaml")
    except Exception as e:
        _BOOT_ERROR = str(e)


def _ensure_ready() -> None:
    if _BOOT_ERROR:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {_BOOT_ERROR}")


def to_synonyms(s: str) -> List[str]:
    """Parse synonyms using [|,;/] separators; lowercased and distinct."""
    if pd.isna(s) or str(s).strip() == "":
        return []
    return parse_synonyms(str(s))


# Precompute lightweight compound dictionaries for quick search and response
COMPOUNDS: List[Dict[str, Any]] = []
if not _BOOT_ERROR:
    for _, row in COMPOUNDS_DF.iterrows():
        COMPOUNDS.append(
            {
                "id": str(row.get("id", "")),
                "name": str(row.get("name", "")),
                "synonyms": to_synonyms(row.get("synonyms", "")),
                "class": str(row.get("class", "")),
                "route": str(row.get("route", "")),
                "common_dose": str(row.get("common_dose", "")),
                "qt_risk": str(row.get("qt_risk", "")),
                "notes": str(row.get("notes", "")),
            }
        )

# Convert DataFrames into more convenient Python structures
INTERACTIONS: List[Dict[str, Any]] = (
    INTERACTIONS_DF.to_dict(orient="records") if not _BOOT_ERROR else []
)
SOURCES: Dict[str, Dict[str, Any]] = (
    {str(row["id"]): row.to_dict() for _, row in SOURCES_DF.iterrows()}
    if not _BOOT_ERROR
    else {}
)

# ── Risk rule configuration ───────────────────────────────────────────────────
sev_map: Dict[str, int] = RULES.get(
    "severity_map", {"None": 0, "Mild": 1, "Moderate": 2, "Severe": 3}
)
evd_map: Dict[str, int] = RULES.get(
    "evidence_grade_map", {"A": 1, "B": 2, "C": 3, "D": 4}
)
weights: Dict[str, float] = RULES.get(
    "weights",
    {"w_sev": 0.9, "w_evd": 0.4, "w_mech": 0.2, "w_dose": 0.3, "w_user": 0.3},
)
buckets: Dict[str, Dict[str, Any]] = RULES.get(
    "buckets",
    {
        "low": {"min": 0.0, "max": 1.5, "label": "Low", "advice": "Low concern. Monitor only."},
        "medium": {"min": 1.5, "max": 3.0, "label": "Medium", "advice": "Use with care."},
        "high": {"min": 3.0, "max": 4.5, "label": "High", "advice": "Avoid combining or consult a clinician."},
        "critical": {"min": 4.5, "max": 100.0, "label": "Critical", "advice": "Do not combine."},
    },
)


def compute_score(
    interaction: Dict[str, Any], doses: Optional[str] = None, flags: Optional[str] = None
) -> tuple[float, str, str]:
    """Compute a risk score and bucket/action for a given interaction record."""
    sev = sev_map.get(str(interaction.get("severity", "None")), 0)
    evd = evd_map.get(str(interaction.get("evidence_grade", "D")), 4)
    mech_tags = (
        str(interaction.get("mechanism_tags", "")).split(";")
        if interaction.get("mechanism_tags")
        else []
    )
    mech_boost = 0.05 * len([m for m in mech_tags if m.strip()])
    dose_factor = 0.1 if doses else 0.0
    user_factor = (
        0.1 * len([f for f in (flags or "").split(",") if f.strip()]) if flags else 0.0
    )
    score = (
        weights.get("w_sev", 0.9) * sev
        + weights.get("w_evd", 0.4) * (1.0 / evd if evd > 0 else 1.0)
        + weights.get("w_mech", 0.2) * mech_boost
        + weights.get("w_dose", 0.3) * dose_factor
        + weights.get("w_user", 0.3) * user_factor
    )
    # Determine bucket from ordered severity thresholds
    bucket_key = "low"
    for bk in ["critical", "high", "medium"]:
        if bk in buckets and score >= buckets[bk]["min"]:
            bucket_key = bk
            break

    bucket_cfg = buckets.get(bucket_key, buckets.get("low", {}))
    bucket_label = bucket_cfg.get("label", "Low")
    action = interaction.get("action") or bucket_cfg.get("advice", "No action needed")
    return round(float(score), 3), bucket_label, str(action)


def find_interaction(a: str, b: str) -> Optional[Dict[str, Any]]:
    """Return the first interaction record matching either ordering of a/b pair."""
    a_norm, b_norm = a.strip().lower(), b.strip().lower()
    for row in INTERACTIONS:
        ca = str(row.get("compound_a", "")).lower()
        cb = str(row.get("compound_b", "")).lower()
        if (ca == a_norm and cb == b_norm) or (ca == b_norm and cb == a_norm):
            return row
    return None


def search_compounds(q: str) -> List[Dict[str, Any]]:
    """Search for compounds whose id, name or synonyms contain the query."""
    ql = q.lower().strip()
    hits: List[Dict[str, Any]] = []
    for c in COMPOUNDS:
        if (
            ql in str(c.get("id", "")).lower()
            or ql in str(c.get("name", "")).lower()
            or any(ql in s.lower() for s in c.get("synonyms", []))
        ):
            hits.append(c)
    hits.sort(key=lambda x: len(x.get("name", "")))
    return hits[:20]


def _build_source_models(interaction: Dict[str, Any]) -> List[InteractionSource]:
    """Resolve source IDs from an interaction row into InteractionSource models."""
    src_ids: List[str] = []
    if interaction.get("source_ids"):
        src_ids = [s.strip() for s in str(interaction["source_ids"]).split(";") if s.strip()]
    models: List[InteractionSource] = []
    for sid in src_ids:
        meta = SOURCES.get(sid)
        if not meta:
            continue
        extra_keys = {
            k: v
            for k, v in meta.items()
            if k not in {"id", "title", "citation", "identifier", "date"}
        }
        models.append(
            InteractionSource(
                id=str(meta.get("id", sid)),
                title=str(meta.get("title", "")) or None,
                citation=str(meta.get("citation", "")) or None,
                identifier=str(meta.get("identifier", "")) or None,
                date=str(meta.get("date", "")) or None,
                extra=extra_keys or None,
            )
        )
    return models


# ── API endpoints ──────────────────────────────────────────────────────────────

@api.get(
    "/search",
    response_model=SearchResponse,
    summary="Search for a compound by id, name or synonym",
    description="Returns a list of up to 20 compounds matching the supplied query.",
)
def search(q: str = Query(..., description="Compound identifier, name or synonym")) -> SearchResponse:
    _ensure_ready()
    hits = search_compounds(q)
    return SearchResponse(
        compounds=[
            CompoundHit(
                id=h["id"],
                name=h["name"],
                synonyms=h.get("synonyms", []),
            )
            for h in hits
        ]
    )


@api.get(
    "/compounds",
    response_model=CompoundsResponse,
    summary="List all known compounds with full metadata",
    description="Returns the full compound library with class, dosage, QT-risk, and notes.",
)
def compounds() -> CompoundsResponse:
    _ensure_ready()
    return CompoundsResponse(
        compounds=[
            CompoundDetail(
                id=c["id"],
                name=c["name"],
                synonyms=c.get("synonyms", []),
                compound_class=c.get("class", ""),
                route=c.get("route", ""),
                common_dose=c.get("common_dose", ""),
                qt_risk=c.get("qt_risk", ""),
                notes=c.get("notes", ""),
            )
            for c in COMPOUNDS
        ]
    )


@api.get(
    "/interaction",
    response_model=InteractionResponse,
    summary="Get the interaction between two compounds",
    description="Compute and return interaction details, score and recommended action for a pair.",
)
def interaction(
    a: str = Query(..., description="Identifier for compound A"),
    b: str = Query(..., description="Identifier for compound B"),
    flags: Optional[str] = Query(None, description="Comma-separated user flags"),
    doses: Optional[str] = Query(None, description="Optional doses to influence scoring"),
) -> InteractionResponse:
    _ensure_ready()
    inter = find_interaction(a, b)
    if not inter:
        raise HTTPException(status_code=404, detail=f"No interaction found for pair: {a} × {b}")
    score, bucket, action = compute_score(inter, doses=doses, flags=flags)
    source_models = _build_source_models(inter)
    detail = InteractionDetail(
        compound_a=str(inter.get("compound_a", a)),
        compound_b=str(inter.get("compound_b", b)),
        severity=str(inter.get("severity", "")) or None,
        evidence_grade=str(inter.get("evidence_grade", "")) or None,
        mechanism_tags=str(inter.get("mechanism_tags", "")) or None,
        effect_summary=str(inter.get("effect_summary", "")) or None,
        source_ids=str(inter.get("source_ids", "")) or None,
        score=score,
        bucket=bucket,
        action_resolved=action,
        sources=source_models,
    )
    return InteractionResponse(pair=InteractionPair(a=a, b=b), interaction=detail)


@api.post(
    "/stack/check",
    response_model=StackCheckResponse,
    summary="Compute an interaction matrix for a stack of compounds",
    description="Given a list of compound identifiers, return pairwise interaction scores.",
)
def stack_check(req: StackCheckRequest | Dict[str, Any]) -> StackCheckResponse:
    _ensure_ready()
    if isinstance(req, dict):
        items_raw = req.get("items", [])
    else:
        items_raw = req.items
    if not isinstance(items_raw, list) or len(items_raw) == 0:
        raise HTTPException(status_code=400, detail="items must be a non-empty list")
    items = [str(item).strip() for item in items_raw]
    n = len(items)
    matrix: List[List[Optional[float]]] = [[None for _ in range(n)] for _ in range(n)]
    cells: List[StackCell] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            inter = find_interaction(items[i], items[j])
            if inter:
                score, bucket, action = compute_score(inter)
                matrix[i][j] = score
                cells.append(
                    StackCell(
                        a=items[i],
                        b=items[j],
                        score=score,
                        bucket=bucket,
                        action=str(action),
                        effect_summary=str(inter.get("effect_summary", "")) or None,
                    )
                )
    return StackCheckResponse(items=items, matrix=matrix, cells=cells)


# ── Legacy root routes for backward compatibility ─────────────────────────────
@app.get("/health")
def _legacy_health():
    return health()

@app.get("/search", include_in_schema=False)
def _legacy_search(q: str):
    return search(q)

@app.get("/interaction", include_in_schema=False)
def _legacy_interaction(a: str, b: str, flags: str | None = None, doses: str | None = None):
    return interaction(a=a, b=b, flags=flags, doses=doses)

@app.post("/stack/check", include_in_schema=False)
def _legacy_stack(req: StackCheckRequest | dict):
    return stack_check(req)

app.include_router(api)
