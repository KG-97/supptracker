from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Optional, Tuple
import os
import csv
import re
import yaml

# Define data models
class Compound(BaseModel):
    id: str
    name: str
    synonyms: List[str] = Field(default_factory=list)
    cls: Optional[str] = None
    typicalDoseAmount: Optional[str] = None
    typicalDoseUnit: Optional[str] = None
    route: Optional[str] = None

class Interaction(BaseModel):
    id: str
    a: str
    b: str
    bidirectional: bool = True
    mechanism: List[str] = Field(default_factory=list)
    severity: Literal['None','Mild','Moderate','Severe']
    evidence: Literal['A','B','C','D']
    effect: str
    action: str
    sources: List[str] = Field(default_factory=list)

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
            raw_synonyms = row.get("synonyms") or ""
            if raw_synonyms:
                parts = re.split(r"[\|,;]", raw_synonyms)
                synonyms = [s.strip() for s in parts if s.strip()]
            else:
                synonyms = []
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

def load_interactions() -> List[dict]:
    interactions: List[dict] = []
    path = os.path.join(DATA_DIR, "interactions.csv")
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mechanisms = [m.strip() for m in row["mechanism"].split("|")] if row.get("mechanism") else []
            sources = [s.strip() for s in row["sources"].split("|")] if row.get("sources") else []
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
    return interactions

def load_sources() -> Dict[str, dict]:
    sources: Dict[str, dict] = {}
    path = os.path.join(DATA_DIR, "sources.csv")
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sources[row["id"]] = row
    return sources

COMPOUNDS = load_compounds()
INTERACTIONS = load_interactions()
SOURCES = load_sources()

# Risk model parameters (from rules.yaml)
DEFAULT_MECHANISM_DELTAS = {
    "CYP3A4_inhibition": 0.6,
    "CYP3A4_induction": 0.6,
    "QT_prolong": 1.0,
    "serotonergic": 1.2,
}
DEFAULT_WEIGHTS = {"severity": 1.0, "evidence": 0.6, "mechanism": 0.4}
DEFAULT_SEVERITY_MAP = {"None": 0, "Mild": 1, "Moderate": 2, "Severe": 3}
DEFAULT_EVIDENCE_MAP = {"A": 1, "B": 2, "C": 3, "D": 4}

RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.yaml")


def load_rules(path: Optional[str] = None) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, int], Dict[str, int]]:
    """Load risk model parameters from YAML configuration."""

    path = path or RULES_PATH
    mechanisms = DEFAULT_MECHANISM_DELTAS.copy()
    weights = DEFAULT_WEIGHTS.copy()
    severity_map = DEFAULT_SEVERITY_MAP.copy()
    evidence_map = DEFAULT_EVIDENCE_MAP.copy()

    if not path:
        return mechanisms, weights, severity_map, evidence_map

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return mechanisms, weights, severity_map, evidence_map
    except (yaml.YAMLError, OSError):
        return mechanisms, weights, severity_map, evidence_map

    if not isinstance(data, dict):
        return mechanisms, weights, severity_map, evidence_map

    mechanisms_cfg = data.get("mechanisms")
    if isinstance(mechanisms_cfg, dict):
        for name, entry in mechanisms_cfg.items():
            delta = None
            if isinstance(entry, dict):
                delta = entry.get("delta")
            else:
                delta = entry
            if delta is None:
                continue
            try:
                mechanisms[name] = float(delta)
            except (TypeError, ValueError):
                continue

    weights_cfg = data.get("weights")
    if isinstance(weights_cfg, dict):
        for key, value in weights_cfg.items():
            if key not in weights:
                continue
            try:
                weights[key] = float(value)
            except (TypeError, ValueError):
                continue

    map_cfg = data.get("map")
    if isinstance(map_cfg, dict):
        severity_cfg = map_cfg.get("severity")
        if isinstance(severity_cfg, dict):
            for key, value in severity_cfg.items():
                try:
                    severity_map[key] = int(value)
                except (TypeError, ValueError):
                    continue
        evidence_cfg = map_cfg.get("evidence")
        if isinstance(evidence_cfg, dict):
            for key, value in evidence_cfg.items():
                try:
                    evidence_map[key] = int(value)
                except (TypeError, ValueError):
                    continue

    return mechanisms, weights, severity_map, evidence_map


def apply_rules(path: Optional[str] = None) -> None:
    """Apply rule configuration from the provided path or defaults."""

    global MECHANISM_DELTAS, WEIGHTS, SEVERITY_MAP, EVIDENCE_MAP
    MECHANISM_DELTAS, WEIGHTS, SEVERITY_MAP, EVIDENCE_MAP = load_rules(path)


apply_rules()

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

    severity_score = SEVERITY_MAP.get(inter.get("severity"), 0)
    evidence_default = EVIDENCE_MAP.get("D", DEFAULT_EVIDENCE_MAP["D"])
    evidence_score = EVIDENCE_MAP.get(inter.get("evidence"), evidence_default)
    mech_sum = sum(MECHANISM_DELTAS.get(m, 0.0) for m in inter.get("mechanism", []))

    severity_weight = WEIGHTS.get("severity", DEFAULT_WEIGHTS["severity"])
    evidence_weight = WEIGHTS.get("evidence", DEFAULT_WEIGHTS["evidence"])
    mechanism_weight = WEIGHTS.get("mechanism", DEFAULT_WEIGHTS["mechanism"])

    if evidence_score:
        evidence_component = (1.0 / evidence_score) * evidence_weight
    else:
        evidence_component = 0.0

    risk = severity_score * severity_weight + evidence_component + mech_sum * mechanism_weight
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
    for inter in INTERACTIONS:
        if (inter["a"] == a_id and inter["b"] == b_id) or (inter["bidirectional"] and inter["a"] == b_id and inter["b"] == a_id):
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
            for inter in INTERACTIONS:
                if (inter["a"] == a_id and inter["b"] == b_id) or (inter["bidirectional"] and inter["a"] == b_id and inter["b"] == a_id):
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
