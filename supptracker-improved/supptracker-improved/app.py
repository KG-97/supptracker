"""
Main FastAPI application for the Supplement Interaction API.

This module wires together the data loading, scoring logic and HTTP endpoints
exposed via FastAPI. It uses Pydantic models defined in ``models.py`` to
enforce strict schema validation and to generate comprehensive API docs.
The application loads CSV/YAML data at startup and supports overriding
the data directory via the ``SUPPTRACKER_DATA_DIR`` environment variable.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import pandas as pd
import yaml, os
from pathlib import Path

# Import models used for request/response validation and OpenAPI generation
from models import (
    SearchResponse,
    InteractionResponse,
    StackCheckRequest,
    StackCheckResponse,
    CompoundHit,
    InteractionPair,
    InteractionDetail,
    InteractionSource,
    StackCell,
)

# Determine the directory where CSV/YAML data files are located. You can set
# the ``SUPPTRACKER_DATA_DIR`` environment variable to override the default
# ``data/`` directory relative to this file. This allows running the API
# against different datasets without changing code.
HERE = Path(__file__).parent
DATA = Path(os.environ.get("SUPPTRACKER_DATA_DIR", HERE / "data"))


def load_csv(name: str) -> pd.DataFrame:
    """Load a CSV file from the configured data directory.

    Parameters
    ----------
    name: str
        Filename of the CSV relative to ``DATA``.

    Returns
    -------
    pandas.DataFrame
        DataFrame containing the parsed CSV contents.

    Raises
    ------
    FileNotFoundError
        If the specified file does not exist.
    """
    p = DATA / name
    if not p.exists():
        raise FileNotFoundError(f"Missing data file: {name} in {DATA}")
    return pd.read_csv(p)


def load_yaml(name: str) -> dict:
    """Load a YAML file from the configured data directory.

    If the file is empty this function returns an empty dict instead of ``None``.
    """
    p = DATA / name
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# Instantiate the FastAPI application with metadata. Increment the version to
# reflect changes to the API surface and behaviour.
app = FastAPI(title="Supplement Interaction API", version="0.2.0")

# Enable permissive CORS by default. In production you may wish to restrict
# origins, methods or headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, str]:
    """Simple health check endpoint used by readiness/liveness probes."""
    return {"status": "ok", "service": "supptracker-backend", "version": app.version}


# Load data into memory at startup. These datasets are immutable and shared
# across requests; they should be treated as read-only.
COMPOUNDS_DF = load_csv("compounds.csv")
INTERACTIONS_DF = load_csv("interactions.csv")
SOURCES_DF = load_csv("sources.csv")
RULES = load_yaml("risk_rules.yaml")


def to_synonyms(s: str) -> List[str]:
    """Parse a semicolon-separated string of synonyms into a list."""
    if pd.isna(s) or str(s).strip() == "":
        return []
    return [x.strip() for x in str(s).split(";") if x.strip()]


# Precompute lightweight compound dictionaries for quick search and response
COMPOUNDS: List[Dict[str, Any]] = []
for _, row in COMPOUNDS_DF.iterrows():
    COMPOUNDS.append(
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "synonyms": to_synonyms(row.get("synonyms", "")),
            "class": row.get("class", ""),
            "route": row.get("route", ""),
            "common_dose": row.get("common_dose", ""),
            "qt_risk": row.get("qt_risk", ""),
            "notes": row.get("notes", ""),
        }
    )

# Convert DataFrames into more convenient Python structures
INTERACTIONS: List[Dict[str, Any]] = INTERACTIONS_DF.to_dict(orient="records")
SOURCES: Dict[str, Dict[str, Any]] = {row["id"]: row for _, row in SOURCES_DF.iterrows()}


# Risk rule configuration with sensible defaults
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
        "low": {
            "max": 0.7,
            "label": "No meaningful interaction",
            "action": "No meaningful interaction",
        },
        "caution": {
            "min": 0.71,
            "max": 1.5,
            "label": "Caution",
            "action": "Monitor",
        },
        "high": {"min": 1.51, "label": "High", "action": "Avoid"},
    },
)


def compute_score(
    interaction: Dict[str, Any], doses: Optional[str] = None, flags: Optional[str] = None
) -> tuple[float, str, str]:
    """Compute a risk score and bucket for a given interaction record."""
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
    low_max = buckets["low"]["max"]
    high_min = buckets["high"]["min"]
    if score <= low_max:
        bucket_label = buckets["low"]["label"]
        action = buckets["low"]["action"]
    elif score >= high_min:
        bucket_label = buckets["high"]["label"]
        action = buckets["high"]["action"]
    else:
        bucket_label = buckets["caution"]["label"]
        action = interaction.get("action", buckets["caution"]["action"])
    return round(float(score), 3), bucket_label, action


def find_interaction(a: str, b: str) -> Optional[Dict[str, Any]]:
    """Return the first interaction record matching either ordering of the pair."""
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
            hits.append(
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "synonyms": c.get("synonyms", []),
                }
            )
    hits.sort(key=lambda x: len(x.get("name", "")))
    return hits[:20]


@app.get(
    "/search",
    response_model=SearchResponse,
    summary="Search for a compound by id, name or synonym",
    description="Returns a list of up to 20 compounds matching the supplied query.",
)
def search(q: str = Query(..., description="Compound identifier, name or synonym")) -> SearchResponse:
    hits = search_compounds(q)
    return SearchResponse(compounds=[CompoundHit(**h) for h in hits])


@app.get(
    "/interaction",
    response_model=InteractionResponse,
    summary="Get the interaction between two compounds",
    description="Compute and return the interaction details, score and recommended action for a pair of compounds.",
)
def interaction(
    a: str = Query(..., description="Identifier for compound A"),
    b: str = Query(..., description="Identifier for compound B"),
    flags: Optional[str] = Query(
        None,
        description="Comma separated list of user flags that may influence scoring",
    ),
    doses: Optional[str] = Query(
        None,
        description="Optional doses used to influence scoring",
    ),
) -> InteractionResponse:
    inter = find_interaction(a, b)
    if not inter:
        raise HTTPException(status_code=404, detail="No interaction found for pair")
    score, bucket, action = compute_score(inter, doses=doses, flags=flags)
    src_ids: List[str] = []
    if inter.get("source_ids"):
        src_ids = [s.strip() for s in str(inter.get("source_ids")).split(";") if s.strip()]
    source_models: List[InteractionSource] = []
    for sid in src_ids:
        meta = SOURCES.get(sid)
        if not meta:
            continue
        extra_keys = {
            k: v
            for k, v in meta.items()
            if k not in {"id", "title", "citation", "identifier", "date"}
        }
        source_models.append(
            InteractionSource(
                id=meta.get("id"),
                title=meta.get("title"),
                citation=meta.get("citation"),
                identifier=meta.get("identifier"),
                date=meta.get("date"),
                extra=extra_keys or None,
            )
        )
    detail = InteractionDetail(
        compound_a=inter.get("compound_a"),
        compound_b=inter.get("compound_b"),
        severity=inter.get("severity"),
        evidence_grade=inter.get("evidence_grade"),
        mechanism_tags=inter.get("mechanism_tags"),
        source_ids=inter.get("source_ids"),
        score=score,
        bucket=bucket,
        action_resolved=action,
        sources=source_models,
    )
    return InteractionResponse(pair=InteractionPair(a=a, b=b), interaction=detail)


@app.post(
    "/stack/check",
    response_model=StackCheckResponse,
    summary="Compute an interaction matrix for a stack of compounds",
    description="Given a list of compound identifiers, compute pairwise interactions and return a square matrix of scores.",
)
def stack_check(req: StackCheckRequest | Dict[str, Any]) -> StackCheckResponse:
    """Compute a pairwise interaction matrix for a list of compounds.

    This function accepts either a validated ``StackCheckRequest`` or a plain
    dictionary.  The latter behaviour exists to support backwards
    compatibility with direct Python calls in the test suite, which invoke
    ``stack_check`` with a simple dict.  When called via FastAPI the request
    body is validated automatically.
    """
    # Normalise input to a list of compound identifiers.  If a raw dict is
    # provided (as in the legacy tests), fall back to extracting the
    # ``items`` key manually.
    if isinstance(req, dict):
        items_raw = req.get("items", [])
    else:
        items_raw = req.items
    # Validate the list
    if not isinstance(items_raw, list) or len(items_raw) == 0:
        raise HTTPException(status_code=400, detail="items must be a non-empty list")
    items = [str(item).strip() for item in items_raw]
    n = len(items)
    matrix: List[List[Optional[float]]] = [[None for _ in range(n)] for __ in range(n)]
    cells: List[StackCell] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a_id = items[i]
            b_id = items[j]
            inter = find_interaction(a_id, b_id)
            if inter:
                score, bucket, action = compute_score(inter, doses=None, flags=None)
                matrix[i][j] = score
                cells.append(StackCell(a=a_id, b=b_id, score=score, bucket=bucket, action=action))
            else:
                matrix[i][j] = None
    return StackCheckResponse(items=items, matrix=matrix, cells=cells)