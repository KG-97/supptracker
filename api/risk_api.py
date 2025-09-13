from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Literal, Dict, Optional, Tuple
import os
import csv

# Define data models
class Compound(BaseModel):
    id: str
    name: str
    synonyms: List[str] = []
    cls: Optional[str] = None
    typicalDoseAmount: Optional[str] = None
    typicalDoseUnit: Optional[str] = None
    route: Optional[str] = None

class Interaction(BaseModel):
    id: str
    a: str
    b: str
    bidirectional: bool = True
    mechanism: List[str] = []
    severity: Literal['None','Mild','Moderate','Severe']
    evidence: Literal['A','B','C','D']
    effect: str
    action: str
    sources: List[str] = []

app = FastAPI()

# Load data from CSV files at startup
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

def load_compounds() -> Dict[str, dict]:
    compounds: Dict[str, dict] = {}
    path = os.path.join(DATA_DIR, "compounds.csv")
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            synonyms = [s.strip() for s in row["synonyms"].split("|")] if row.get("synonyms") else []
            compounds[row["id"]] = {
                "id": row["id"],
                "name": row["name"],
                "synonyms": synonyms,
                "class": row.get("class") or None,
                "typicalDoseAmount": row.get("typicalDoseAmount") or None,
                "typicalDoseUnit": row.get("typicalDoseUnit") or None,
                "route": row.get("route") or None,
            }
    return compounds

def load_interactions() -> Tuple[List[dict], Dict[Tuple[str, str], dict]]:
    """Load interactions and build a lookup dictionary."""
    interactions: List[dict] = []
    inter_map: Dict[Tuple[str, str], dict] = {}
    path = os.path.join(DATA_DIR, "interactions.csv")
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mechanisms = [m.strip() for m in row["mechanism"].split("|")] if row.get("mechanism") else []
            sources = [s.strip() for s in row["sources"].split("|")] if row.get("sources") else []
            inter = {
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
            }
            interactions.append(inter)
            inter_map[(inter["a"], inter["b"])] = inter
            if inter["bidirectional"]:
                inter_map[(inter["b"], inter["a"])] = inter
    return interactions, inter_map

def load_sources() -> Dict[str, dict]:
    sources: Dict[str, dict] = {}
    path = os.path.join(DATA_DIR, "sources.csv")
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sources[row["id"]] = row
    return sources

COMPOUNDS = load_compounds()
INTERACTIONS, INTERACTION_MAP = load_interactions()
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
    """Resolve a compound id or name/synonym to its id."""
    if identifier in COMPOUNDS:
        return identifier
    ident_lower = identifier.lower()
    for cid, comp in COMPOUNDS.items():
        if comp["name"].lower() == ident_lower or ident_lower in [s.lower() for s in comp["synonyms"]]:
            return cid
    return None

def compute_risk(inter: dict) -> float:
    """Compute risk score for an interaction."""
    severity_score = SEVERITY_MAP.get(inter["severity"], 0)
    evidence_score = EVIDENCE_MAP.get(inter["evidence"], 4)
    mech_sum = sum(MECHANISM_DELTAS.get(m, 0) for m in inter["mechanism"])
    risk = severity_score * WEIGHTS["severity"] + (1.0 / evidence_score) * WEIGHTS["evidence"] + mech_sum * WEIGHTS["mechanism"]
    return round(risk, 2)

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/search")
def search(q: str):
    """Search compounds by name or synonym."""
    q_lower = q.lower()
    results: List[dict] = []
    for comp in COMPOUNDS.values():
        if q_lower in comp["name"].lower() or any(q_lower in syn.lower() for syn in comp["synonyms"]):
            results.append(comp)
    return {"results": results}

@app.get("/api/interaction")
def interaction(a: str, b: str):
    """Get interaction details between two compounds by id or name."""
    a_id = resolve_compound(a)
    b_id = resolve_compound(b)
    if not a_id or not b_id:
        raise HTTPException(status_code=404, detail="One or both compounds not found")
    inter = INTERACTION_MAP.get((a_id, b_id))
    if inter:
        risk_score = compute_risk(inter)
        sources_detail = [SOURCES[sid] for sid in inter["sources"] if sid in SOURCES]
        return {"interaction": inter, "risk_score": risk_score, "sources": sources_detail}
    return {"message": "No known interaction"}

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
            inter = INTERACTION_MAP.get((a_id, b_id))
            if inter:
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
