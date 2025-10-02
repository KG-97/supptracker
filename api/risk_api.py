"""Risk API for supplement interaction tracking.

Provides endpoints for searching compounds, checking interactions,
and calculating risk scores based on drug interaction data.
"""
from pathlib import Path
from typing import Literal, Optional

import csv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# Define data models
class Compound(BaseModel):
    """Model for supplement/compound data."""
    id: str
    name: str
    synonyms: list[str] = Field(default_factory=list)
    cls: Optional[str] = Field(default=None, alias="class")
    typicalDoseAmount: Optional[str] = None
    typicalDoseUnit: Optional[str] = None
    route: Optional[str] = None

    class Config:
        populate_by_name = True


class Interaction(BaseModel):
    """Model for compound interaction data."""
    id: str
    a: str
    b: str
    bidirectional: bool = True
    mechanism: list[str] = Field(default_factory=list)
    severity: Literal["None", "Mild", "Moderate", "Severe"]
    evidence: Literal["A", "B", "C", "D"]
    effect: str
    action: str
    sources: list[str] = Field(default_factory=list)


class StackRequest(BaseModel):
    """Request model for stack checking endpoint."""
    compounds: list[str]


app = FastAPI()

# Load data from CSV files at startup
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


def load_compounds() -> dict[str, dict]:
    """Load compound data from CSV file.
    
    Returns:
        Dictionary mapping compound IDs to compound data.
        
    Raises:
        FileNotFoundError: If compounds.csv is not found.
    """
    compounds: dict[str, dict] = {}
    path = DATA_DIR / "compounds.csv"
    
    try:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                synonyms = (
                    [s.strip() for s in row["synonyms"].split("|")] 
                    if row.get("synonyms") 
                    else []
                )
                compounds[row["id"]] = {
                    "id": row["id"],
                    "name": row["name"],
                    "synonyms": synonyms,
                    "class": row.get("class") or None,
                    "typicalDoseAmount": row.get("typicalDoseAmount") or None,
                    "typicalDoseUnit": row.get("typicalDoseUnit") or None,
                    "route": row.get("route") or None,
                }
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Compounds data file not found: {path}") from exc
    
    return compounds


def load_interactions() -> list[dict]:
    """Load interaction data from CSV file.
    
    Returns:
        List of interaction dictionaries.
        
    Raises:
        FileNotFoundError: If interactions.csv is not found.
    """
    interactions: list[dict] = []
    path = DATA_DIR / "interactions.csv"
    
    try:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mechanisms = (
                    [m.strip() for m in row["mechanism"].split("|")] 
                    if row.get("mechanism") 
                    else []
                )
                sources = (
                    [s.strip() for s in row["sources"].split("|")] 
                    if row.get("sources") 
                    else []
                )
                interactions.append({
                    "id": row["id"],
                    "a": row["a"],
                    "b": row["b"],
                    "bidirectional": row.get("bidirectional", "").lower() == "true",
                    "mechanism": mechanisms,
                    "severity": row["severity"],
                    "evidence": row["evidence"],
                    "effect": row["effect"],
                    "action": row["action"],
                    "sources": sources,
                })
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Interactions data file not found: {path}") from exc
    
    return interactions


def load_sources() -> dict[str, dict]:
    """Load source reference data from CSV file.
    
    Returns:
        Dictionary mapping source IDs to source data.
        
    Raises:
        FileNotFoundError: If sources.csv is not found.
    """
    sources: dict[str, dict] = {}
    path = DATA_DIR / "sources.csv"
    
    try:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sources[row["id"]] = row
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Sources data file not found: {path}") from exc
    
    return sources


# Initialize data at module level
COMPOUNDS = load_compounds()
INTERACTIONS = load_interactions()
SOURCES = load_sources()

# Risk model parameters (from rules.yaml)
MECHANISM_DELTAS = {
    "CYP3A4_inhibition": 0.6,
    "CYP3A4_induction": 0.6,
    "QT_prolong": 1.0,
    "serotonergic": 1.2,
}
WEIGHTS = {"severity": 1.0, "evidence": 0.6, "mechanism": 0.4}
SEVERITY_MAP = {"None": 0, "Mild": 1, "Moderate": 2, "Severe": 3}
EVIDENCE_MAP = {"A": 1, "B": 2, "C": 3, "D": 4}


def resolve_compound(identifier: str) -> Optional[str]:
    """Resolve a compound ID or name/synonym to its ID.
    
    Args:
        identifier: Compound ID, name, or synonym to resolve.
        
    Returns:
        Compound ID if found, None otherwise.
    """
    if identifier in COMPOUNDS:
        return identifier
    
    ident_lower = identifier.lower()
    for cid, comp in COMPOUNDS.items():
        if comp["name"].lower() == ident_lower:
            return cid
        if ident_lower in [s.lower() for s in comp["synonyms"]]:
            return cid
    
    return None


def compute_risk(inter: dict) -> float:
    """Compute risk score for an interaction.
    
    Args:
        inter: Interaction dictionary containing severity, evidence, and mechanism data.
        
    Returns:
        Calculated risk score rounded to 2 decimal places.
    """
    severity_score = SEVERITY_MAP.get(inter["severity"], 0)
    evidence_score = EVIDENCE_MAP.get(inter["evidence"], 4)
    mech_sum = sum(MECHANISM_DELTAS.get(m, 0) for m in inter["mechanism"])
    
    risk = (
        severity_score * WEIGHTS["severity"]
        + (1.0 / evidence_score) * WEIGHTS["evidence"]
        + mech_sum * WEIGHTS["mechanism"]
    )
    return round(risk, 2)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Health check endpoint.
    
    Returns:
        Status dictionary indicating API health.
    """
    return {"status": "ok"}


@app.get("/api/search")
def search(q: str) -> dict[str, list[dict]]:
    """Search compounds by name or synonym.
    
    Args:
        q: Search query string.
        
    Returns:
        Dictionary containing list of matching compounds.
    """
    q_lower = q.lower()
    results: list[dict] = []
    
    for comp in COMPOUNDS.values():
        name_match = q_lower in comp["name"].lower()
        synonym_match = any(
            q_lower in syn.lower() for syn in comp["synonyms"]
        )
        if name_match or synonym_match:
            results.append(comp)
    
    return {"results": results}


@app.get("/api/interaction")
def interaction(a: str, b: str) -> dict:
    """Get interaction details between two compounds.
    
    Args:
        a: First compound (ID or name).
        b: Second compound (ID or name).
        
    Returns:
        Interaction details including risk score and sources.
        
    Raises:
        HTTPException: If one or both compounds are not found.
    """
    a_id = resolve_compound(a)
    b_id = resolve_compound(b)
    
    if not a_id or not b_id:
        raise HTTPException(
            status_code=404,
            detail="One or both compounds not found"
        )
    
    for inter in INTERACTIONS:
        # Check both directions if bidirectional
        matches_forward = inter["a"] == a_id and inter["b"] == b_id
        matches_reverse = (
            inter["bidirectional"] 
            and inter["a"] == b_id 
            and inter["b"] == a_id
        )
        
        if matches_forward or matches_reverse:
            risk_score = compute_risk(inter)
            sources_detail = [
                SOURCES[sid] for sid in inter["sources"] if sid in SOURCES
            ]
            return {
                "interaction": inter,
                "risk_score": risk_score,
                "sources": sources_detail
            }
    
    return {"message": "No known interaction"}


@app.post("/api/stack/check")
def check_stack(payload: StackRequest) -> dict[str, list[dict]]:
    """Check interactions within a stack of compounds.
    
    Args:
        payload: Request containing list of compound identifiers.
        
    Returns:
        Dictionary containing list of detected interactions.
        
    Raises:
        HTTPException: If any compound is not found.
    """
    ids: list[str] = []
    
    # Resolve all compound identifiers
    for ident in payload.compounds:
        cid = resolve_compound(ident)
        if not cid:
            raise HTTPException(
                status_code=404,
                detail=f"Compound not found: {ident}"
            )
        ids.append(cid)
    
    # Check all pairwise interactions
    interactions_out: list[dict] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id = ids[i]
            b_id = ids[j]
            
            for inter in INTERACTIONS:
                matches_forward = inter["a"] == a_id and inter["b"] == b_id
                matches_reverse = (
                    inter["bidirectional"] 
                    and inter["a"] == b_id 
                    and inter["b"] == a_id
                )
                
                if matches_forward or matches_reverse:
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
