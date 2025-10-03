import csv
import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="SuppTracker Risk API",
    description="Supplement interaction risk analysis API",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from frontend build if available
FRONTEND_DIST = Path(os.getenv("SUPPTRACKER_FRONTEND_DIST", "frontend_dist"))
STATIC_ASSETS_DIR = FRONTEND_DIST / "assets"

if STATIC_ASSETS_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_ASSETS_DIR), name="static")
else:
    logger.warning(
        "Static assets directory not found at %s. Skipping static mount.",
        STATIC_ASSETS_DIR,
    )

# Default scoring configuration ---------------------------------------------------------
DATA_DIR = Path(os.getenv("SUPPTRACKER_DATA_DIR", "data"))

DEFAULT_MECHANISM_DELTAS: Dict[str, float] = {
    "pharmacokinetic": 0.6,
    "pharmacodynamic": 0.8,
    "additive": 0.5,
    "synergistic": 1.0,
    "unknown": 0.3,
}

DEFAULT_WEIGHTS: Dict[str, float] = {
    "severity": 1.5,
    "evidence": 0.8,
    "mechanism": 0.4,
}

DEFAULT_SEVERITY_MAP: Dict[str, float] = {
    "None": 0.0,
    "Mild": 1.0,
    "Moderate": 2.0,
    "Severe": 3.0,
}

DEFAULT_EVIDENCE_MAP: Dict[str, float] = {
    "A": 1.0,
    "B": 2.0,
    "C": 3.0,
    "D": 4.0,
}

DEFAULT_FORMULA_SOURCE = (
    "severity_component + mechanism_component + evidence_component"
)


def _default_formula(
    *,
    severity: float,
    weights: SimpleNamespace,
    mech_sum: float,
    evidence_component: float,
) -> float:
    severity_weight = getattr(weights, "severity", DEFAULT_WEIGHTS["severity"])
    mechanism_weight = getattr(weights, "mechanism", DEFAULT_WEIGHTS["mechanism"])
    severity_component = severity * severity_weight
    mechanism_component = mech_sum * mechanism_weight
    return severity_component + mechanism_component + evidence_component


MECHANISM_DELTAS: Dict[str, float] = DEFAULT_MECHANISM_DELTAS.copy()
WEIGHTS: Dict[str, float] = DEFAULT_WEIGHTS.copy()
SEVERITY_MAP: Dict[str, float] = DEFAULT_SEVERITY_MAP.copy()
EVIDENCE_MAP: Dict[str, float] = DEFAULT_EVIDENCE_MAP.copy()
RISK_FORMULA = _default_formula
FORMULA_SOURCE = DEFAULT_FORMULA_SOURCE


def _resolve_config_path(path: Optional[str]) -> Optional[Path]:
    if path:
        return Path(path)
    env_path = os.getenv("RISK_RULES_PATH")
    if env_path:
        return Path(env_path)
    candidate = DATA_DIR / "risk_rules.yaml"
    return candidate if candidate.exists() else None


def _parse_synonyms(value: str) -> List[str]:
    if not value:
        return []
    reader = csv.reader([value])
    try:
        row = next(reader)
    except StopIteration:
        return []
    if len(row) == 1:
        row = [part.strip() for part in row[0].split(",")]
    else:
        row = [item.strip() for item in row]
    return [item for item in row if item]


def _coerce_iterable(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return value
    return []


def load_compounds(data_dir: Optional[str | Path] = None) -> Dict[str, Dict[str, Any]]:
    directory = Path(data_dir) if data_dir is not None else Path(DATA_DIR)
    compounds: Dict[str, Dict[str, Any]] = {}

    csv_path = directory / "compounds.csv"
    json_path = directory / "compounds.json"

    if csv_path.exists():
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    compound_id = row.get("id")
                    if not compound_id:
                        continue
                    synonyms = _parse_synonyms(row.get("synonyms", ""))
                    compounds[compound_id] = {
                        **{k: v for k, v in row.items() if v not in (None, "")},
                        "id": compound_id,
                        "name": row.get("name") or compound_id,
                        "synonyms": synonyms,
                    }
            return compounds
        except Exception as exc:  # pragma: no cover - logged for diagnostics
            logger.error("Failed to load compounds CSV: %s", exc)

    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            for entry in data:
                compound_id = entry.get("id")
                if not compound_id:
                    continue
                synonyms = entry.get("synonyms") or entry.get("aliases") or []
                compounds[compound_id] = {
                    **entry,
                    "id": compound_id,
                    "name": entry.get("name") or compound_id,
                    "synonyms": list(_coerce_iterable(synonyms)),
                }
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load compounds JSON: %s", exc)

    return compounds


def load_interactions(data_dir: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    directory = Path(data_dir) if data_dir is not None else Path(DATA_DIR)
    csv_path = directory / "interactions.csv"
    json_path = directory / "interactions.json"

    if csv_path.exists():
        interactions: List[Dict[str, Any]] = []
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    mechanisms = _parse_synonyms(row.get("mechanism", ""))
                    interactions.append(
                        {
                            **{k: v for k, v in row.items() if v not in (None, "")},
                            "mechanism": mechanisms,
                        }
                    )
            return interactions
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load interactions CSV: %s", exc)

    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load interactions JSON: %s", exc)
    return []


def load_sources(data_dir: Optional[str | Path] = None) -> Dict[str, Dict[str, Any]]:
    directory = Path(data_dir) if data_dir is not None else Path(DATA_DIR)
    csv_path = directory / "sources.csv"
    json_path = directory / "sources.json"

    if csv_path.exists():
        sources: Dict[str, Dict[str, Any]] = {}
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    source_id = row.get("id")
                    if not source_id:
                        continue
                    sources[source_id] = {
                        **{k: v for k, v in row.items() if v not in (None, "")},
                        "id": source_id,
                    }
            return sources
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load sources CSV: %s", exc)

    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            return {item["id"]: item for item in data if "id" in item}
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load sources JSON: %s", exc)
    return {}


def load_rules(path: Optional[str] = None) -> Tuple[
    Dict[str, float],
    Dict[str, float],
    Dict[str, float],
    Dict[str, float],
    Any,
    str,
]:
    config_path = _resolve_config_path(path)
    mechanisms = DEFAULT_MECHANISM_DELTAS.copy()
    weights = DEFAULT_WEIGHTS.copy()
    severity_map = DEFAULT_SEVERITY_MAP.copy()
    evidence_map = DEFAULT_EVIDENCE_MAP.copy()
    formula = _default_formula
    formula_source = DEFAULT_FORMULA_SOURCE

    if not config_path or not config_path.exists():
        return mechanisms, weights, severity_map, evidence_map, formula, formula_source

    try:
        with open(config_path, encoding="utf-8") as fh:
            content = yaml.safe_load(fh) or {}
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to load rules config %s: %s", config_path, exc)
        return mechanisms, weights, severity_map, evidence_map, formula, formula_source

    try:
        raw_mechanisms = content.get("mechanisms", {}) or {}
        for name, value in raw_mechanisms.items():
            if isinstance(value, dict):
                delta = value.get("delta")
                if isinstance(delta, (int, float)):
                    mechanisms[name] = float(delta)
            elif isinstance(value, (int, float)):
                mechanisms[name] = float(value)

        weights.update(content.get("weights", {}) or {})

        severity_section = content.get("map", {}).get("severity")
        if isinstance(severity_section, dict):
            severity_map.update(severity_section)

        evidence_section = content.get("map", {}).get("evidence")
        if isinstance(evidence_section, dict):
            evidence_map.update(evidence_section)

        formula_text = content.get("formula")
        if isinstance(formula_text, str) and formula_text.strip():
            compiled = compile(formula_text, "<risk-formula>", "eval")

            def custom_formula(
                *,
                severity: float,
                weights: SimpleNamespace,
                mech_sum: float,
                evidence_component: float,
            ) -> float:
                safe_globals = {"__builtins__": {"max": max, "min": min, "abs": abs}}
                safe_locals = {
                    "severity": severity,
                    "weights": weights,
                    "mech_sum": mech_sum,
                    "evidence_component": evidence_component,
                }
                return eval(compiled, safe_globals, safe_locals)  # noqa: S307

            formula = custom_formula
            formula_source = formula_text
    except Exception as exc:  # pragma: no cover
        logger.error("Invalid rules config %s: %s", config_path, exc)
        return (
            DEFAULT_MECHANISM_DELTAS.copy(),
            DEFAULT_WEIGHTS.copy(),
            DEFAULT_SEVERITY_MAP.copy(),
            DEFAULT_EVIDENCE_MAP.copy(),
            _default_formula,
            DEFAULT_FORMULA_SOURCE,
        )

    return mechanisms, weights, severity_map, evidence_map, formula, formula_source


def apply_rules(path: Optional[str] = None) -> None:
    global MECHANISM_DELTAS, WEIGHTS, SEVERITY_MAP, EVIDENCE_MAP, RISK_FORMULA, FORMULA_SOURCE
    (
        MECHANISM_DELTAS,
        WEIGHTS,
        SEVERITY_MAP,
        EVIDENCE_MAP,
        RISK_FORMULA,
        FORMULA_SOURCE,
    ) = load_rules(path)



# Global data stores
COMPOUNDS: Dict[str, Dict[str, Any]] = {}
INTERACTIONS: List[Dict[str, Any]] = []
SOURCES: Dict[str, Dict[str, Any]] = {}


def load_data() -> None:
    """Load all data files into module-level caches."""
    global COMPOUNDS, INTERACTIONS, SOURCES

    COMPOUNDS = load_compounds()
    INTERACTIONS = load_interactions()
    SOURCES = load_sources()

    logger.info(
        "Loaded %s compounds, %s interactions, %s sources",
        len(COMPOUNDS),
        len(INTERACTIONS),
        len(SOURCES),
    )


# Load data and rules on startup
load_data()
apply_rules()

# Helper functions
def resolve_compound(identifier: str) -> Optional[str]:
    """Resolve compound by ID, name, or synonym."""
    if not identifier:
        return None

    if identifier in COMPOUNDS:
        return identifier

    identifier_lower = identifier.lower()
    for comp_id, comp in COMPOUNDS.items():
        name = str(comp.get("name", "")).lower()
        if name == identifier_lower:
            return comp_id

        for synonym in _coerce_iterable(comp.get("synonyms") or comp.get("aliases")):
            if str(synonym).lower() == identifier_lower:
                return comp_id

    return None

def _lookup_score(mapping: Dict[str, float], label: Any, fallback: Dict[str, float]) -> float:
    if label is None:
        return 0.0
    if isinstance(label, (int, float)):
        return float(label)

    label_str = str(label)
    if label_str in mapping:
        return float(mapping[label_str])

    for key, value in mapping.items():
        if key.lower() == label_str.lower():
            return float(value)

    for key, value in fallback.items():
        if key.lower() == label_str.lower():
            return float(value)

    return 0.0


def compute_risk(interaction: Dict[str, Any]) -> float:
    """Compute numerical risk score from interaction data."""
    severity_value = _lookup_score(SEVERITY_MAP, interaction.get("severity"), DEFAULT_SEVERITY_MAP)
    mechanisms = [str(m) for m in _coerce_iterable(interaction.get("mechanism"))]
    mech_sum = 0.0
    for mechanism in mechanisms:
        mech_sum += MECHANISM_DELTAS.get(
            mechanism,
            MECHANISM_DELTAS.get(mechanism.lower(), 0.0),
        )

    evidence_label = interaction.get("evidence")
    evidence_value = _lookup_score(EVIDENCE_MAP, evidence_label, DEFAULT_EVIDENCE_MAP)
    if evidence_value:
        evidence_weight = WEIGHTS.get("evidence", DEFAULT_WEIGHTS["evidence"])
        evidence_component = (1 / float(evidence_value)) * evidence_weight
    else:
        fallback_value = max(EVIDENCE_MAP.values() or [1.0])
        evidence_weight = WEIGHTS.get("evidence", DEFAULT_WEIGHTS["evidence"])
        evidence_component = (1 / float(fallback_value)) * evidence_weight

    weights_ns = SimpleNamespace(**WEIGHTS)
    raw_score = RISK_FORMULA(
        severity=severity_value,
        weights=weights_ns,
        mech_sum=mech_sum,
        evidence_component=evidence_component,
    )
    return round(float(raw_score), 2)

# API Routes
@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "compounds_loaded": len(COMPOUNDS),
        "interactions_loaded": len(INTERACTIONS),
        "sources_loaded": len(SOURCES)
    }

@app.get("/api/compounds")
def list_compounds():
    """Get all compounds."""
    return {"compounds": list(COMPOUNDS.values())}


@app.get("/api/interactions")
def list_interactions():
    """Get all known interactions including computed risk scores."""
    interactions_with_scores = []
    for interaction in INTERACTIONS:
        record = interaction.copy()
        record["risk_score"] = compute_risk(interaction)
        interactions_with_scores.append(record)

    return {"interactions": interactions_with_scores}

@app.get("/api/compounds/{compound_id}")
def get_compound(compound_id: str):
    """Get specific compound by ID."""
    if compound_id not in COMPOUNDS:
        raise HTTPException(status_code=404, detail="Compound not found")
    return COMPOUNDS[compound_id]

@app.get("/api/search")
def search(
    q: Optional[str] = Query(None, min_length=1),
    query: Optional[str] = Query(None, min_length=1),
    limit: int = Query(10, ge=1, le=50),
):
    """Search compounds by name or synonym."""
    search_term = query or q
    if not search_term:
        raise HTTPException(status_code=422, detail="Missing search parameter")

    query_lower = search_term.lower()
    results = []
    
    for comp in COMPOUNDS.values():
        # Check name match
        name = comp.get("name", "").lower()
        if query_lower in name:
            results.append(comp)
            continue
        
        # Check alias matches
        aliases = comp.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and query_lower in alias.lower():
                    results.append(comp)
                    break
    
    # Sort by relevance (exact matches first)
    results.sort(key=lambda x: (
        x.get("name", "").lower() != query_lower,
        x.get("name", "").lower().find(query_lower)
    ))
    
    return {"results": results[:limit]}

@app.get("/api/interaction")
def interaction(a: str, b: str):
    """Get interaction details between two compounds by id or name."""
    a_id = resolve_compound(a)
    b_id = resolve_compound(b)
    if not a_id or not b_id:
        raise HTTPException(status_code=404, detail="One or both compounds not found")
    
    for inter in INTERACTIONS:
        if (inter["a"] == a_id and inter["b"] == b_id) or (inter.get("bidirectional", False) and inter["a"] == b_id and inter["b"] == a_id):
            risk_score = compute_risk(inter)
            sources_detail = [SOURCES[sid] for sid in inter.get("sources", []) if sid in SOURCES]
            return {"interaction": inter, "risk_score": risk_score, "sources": sources_detail}
    
    raise HTTPException(status_code=404, detail="No known interaction")

class StackRequest(BaseModel):
    compounds: List[str]

@app.post("/api/stack/check")
def check_stack(payload: StackRequest):
    """Check interactions within a stack of compounds."""
    ids: List[str] = []
    for ident in payload.compounds:
        cid = resolve_compound(ident)
        if not cid:
            raise HTTPException(status_code=404, detail=f"Compound not found: {ident}")
        ids.append(cid)
    
    interactions_out: List[dict] = []
    for i in range(len(ids)):
        for j in range(i+1, len(ids)):
            a_id = ids[i]
            b_id = ids[j]
            for inter in INTERACTIONS:
                if (inter["a"] == a_id and inter["b"] == b_id) or (inter.get("bidirectional", False) and inter["a"] == b_id and inter["b"] == a_id):
                    interactions_out.append({
                        "a": a_id,
                        "b": b_id,
                        "severity": inter["severity"],
                        "evidence": inter["evidence"],
                        "effect": inter["effect"],
                        "action": inter["action"],
                        "risk_score": compute_risk(inter),
                    })
    
    return {"interactions": interactions_out}

# SPA fallback route - must be last
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str, request: Request):
    """Serve React app for all non-API routes (SPA fallback)."""
    # Skip API routes
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Check if it's a static file request
    static_file_path = FRONTEND_DIST / full_path
    if static_file_path.is_file():
        return FileResponse(static_file_path)

    # Serve index.html for all other routes (SPA)
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.is_file():
        logger.warning("SPA index file not found at %s", index_file)
        raise HTTPException(status_code=404, detail="Frontend not built")

    return FileResponse(index_file)
