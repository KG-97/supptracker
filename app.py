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

from data_loader import load_all_data
from scoring import make_scoring_engine

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


# ── Data loading ──────────────────────────────────────────────────────────────
_data = load_all_data()

_BOOT_ERROR: str = _data["boot_error"]
COMPOUNDS: List[Dict[str, Any]] = _data["compounds"]
INTERACTIONS: List[Dict[str, Any]] = _data["interactions"]
SOURCES: Dict[str, Dict[str, Any]] = _data["sources"]
INTERACTION_INDEX: Dict[tuple, Dict[str, Any]] = _data["interaction_index"]

# ── Scoring engine ────────────────────────────────────────────────────────────
_scorer = make_scoring_engine(_data["rules"]) if not _BOOT_ERROR else None


# ── FastAPI app ───────────────────────────────────────────────────────────────
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


def _ensure_ready() -> None:
    if _BOOT_ERROR:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {_BOOT_ERROR}")


def compute_score(
    interaction: Dict[str, Any], doses: Optional[str] = None, flags: Optional[str] = None
) -> tuple[float, str, str]:
    """Delegate to the scoring engine (kept as module-level function for backward compat)."""
    assert _scorer is not None
    return _scorer.compute_score(interaction, doses=doses, flags=flags)


def find_interaction(a: str, b: str) -> Optional[Dict[str, Any]]:
    """Return the interaction record matching either ordering of a/b pair using O(1) index."""
    a_norm, b_norm = a.strip().lower(), b.strip().lower()
    key = (min(a_norm, b_norm), max(a_norm, b_norm))
    return INTERACTION_INDEX.get(key)


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

@api.get("/health")
def health() -> Dict[str, str]:
    """Simple health check endpoint used by readiness/liveness probes."""
    return {"status": "ok", "service": "supptracker-backend", "version": app.version}


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
        return InteractionResponse(pair=InteractionPair(a=a, b=b), interaction=None, found=False)
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
