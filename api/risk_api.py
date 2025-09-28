from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Optional, Tuple, Callable, Any
from pathlib import Path
import logging
import os
import csv
import re
import yaml
import ast
from types import SimpleNamespace
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
class StackRequest(BaseModel):
    items: List[str] = Field(..., description="List of compound IDs or names")
logger = logging.getLogger("supptracker")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)
app = FastAPI()
# Paths and data helpers
BASE_DIR: Path = Path(__file__).resolve().parent.parent
# Support both legacy and new env vars, with new one taking precedence
DATA_DIR: Path = Path(
    os.environ.get("SUPPTRACKER_DATA_DIR",
                   os.environ.get("SUPPTRACKER_DATA", BASE_DIR / "data"))
).expanduser().resolve()
def get_data_dir(override: Optional[str] = None) -> Path:
    """Return the directory that contains the seed CSV files."""
    base = Path(override) if override else Path(DATA_DIR)
    return base.expanduser().resolve()
# Load rules/config
DEFAULT_WEIGHTS = {"severity": 1.0, "evidence": 1.0, "mechanism": 1.0}
MECHANISM_DELTAS: Dict[str, float] = {}
WEIGHTS: Dict[str, float] = {}
RISK_FORMULA: Optional[Callable[..., float]] = None
def _load_rules():
    global MECHANISM_DELTAS, WEIGHTS, RISK_FORMULA
    rules_path = get_data_dir() / "rules.yaml"
    # Also allow api/rules.yaml in repo
    if not rules_path.exists():
        alt = BASE_DIR / "api" / "rules.yaml"
        if alt.exists():
            rules_path = alt
    if rules_path.exists():
        with open(rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        MECHANISM_DELTAS = {**(data.get("mechanisms") or {})}
        WEIGHTS = {**DEFAULT_WEIGHTS, **(data.get("weights") or {})}
        # risk_formula may be a python expression using names in context
        rf = data.get("risk_formula")
        if rf:
            try:
                RISK_FORMULA = eval(rf)
            except Exception:
                RISK_FORMULA = None
    else:
        MECHANISM_DELTAS = {}
        WEIGHTS = {**DEFAULT_WEIGHTS}
        RISK_FORMULA = None
def _default_formula(**ctx: Any) -> float:
    # Simple additive model
    return float(ctx.get("severity_component", 0.0) + ctx.get("evidence_component", 0.0) + ctx.get("mechanism_component", 0.0))
# Load datasets
COMPOUNDS: Dict[str, Dict[str, Any]] = {}
INTERACTIONS: Dict[Tuple[str, str], Dict[str, Any]] = {}
def _normalise_name(s: str) -> str:
    # normalise delimiters like '|' in synonyms elsewhere, but for name lookup, lower and strip spaces
    return re.sub(r"\s+", " ", s).strip().lower()
def _load_compounds():
    path = get_data_dir() / "compounds.csv"
    if not path.exists():
        # also allow repo data
        alt = BASE_DIR / "data" / "compounds.csv"
        path = alt if alt.exists() else path
    if not path.exists():
        logger.warning("compounds.csv not found at %s", path)
        return
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row.get("id") or row.get("ID") or row.get("Id")
            if not cid:
                continue
            name = row.get("name") or row.get("Name") or ""
            # synonyms may be pipe-delimited or comma-delimited; support both
            syn_raw = row.get("synonyms") or row.get("Synonyms") or ""
            # split on pipes or commas
            parts = [p.strip() for p in re.split(r"\||,", syn_raw) if p.strip()]
            comp = {
                "id": cid,
                "name": name,
                "synonyms": parts,
                "cls": row.get("cls") or row.get("class"),
                "typicalDoseAmount": row.get("typicalDoseAmount"),
                "typicalDoseUnit": row.get("typicalDoseUnit"),
                "route": row.get("route"),
            }
            COMPOUNDS[cid] = comp
            # index by name and synonyms for resolution
            COMPOUNDS[_normalise_name(name)] = comp
            for s in parts:
                COMPOUNDS[_normalise_name(s)] = comp
def _load_interactions():
    path = get_data_dir() / "interactions.csv"
    if not path.exists():
        alt = BASE_DIR / "data" / "interactions.csv"
        path = alt if alt.exists() else path
    if not path.exists():
        logger.warning("interactions.csv not found at %s", path)
        return
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            a = row.get("a") or row.get("A")
            b = row.get("b") or row.get("B")
            if not a or not b:
                continue
            key = (a, b)
            inter = {
                "id": row.get("id") or f"{a}-{b}",
                "a": a,
                "b": b,
                "bidirectional": (row.get("bidirectional") or "true").strip().lower() in {"1","true","yes","y"},
                "mechanism": [m.strip() for m in re.split(r"\||,", row.get("mechanism") or "") if m.strip()],
                "severity": row.get("severity") or "None",
                "evidence": row.get("evidence") or "D",
                "effect": row.get("effect") or "",
                "action": row.get("action") or "",
                "sources": [s.strip() for s in re.split(r"\||,", row.get("sources") or "") if s.strip()],
            }
            INTERACTIONS[key] = inter
            if inter["bidirectional"]:
                INTERACTIONS[(b, a)] = inter
_load_rules()
_load_compounds()
_load_interactions()
@app.get("/api/health")
def health():
    return {"status": "ok"}
@app.get("/api/search")
def search(q: str):
    """Search compounds by name or synonym."""
    q_lower = q.lower()
    results: List[dict] = []
    seen = set()
    for comp in {id_: c for id_, c in COMPOUNDS.items() if isinstance(id_, str) and id_.lower() == id_}.values():
        # the comprehension above is to iterate unique dict values via canonical id keys
        name_match = q_lower in (comp.get("name") or "").lower()
        syn_match = any(q_lower in (syn or "").lower() for syn in comp.get("synonyms", []))
        if name_match or syn_match:
            cid = comp["id"]
            if cid not in seen:
                results.append(comp)
                seen.add(cid)
    return {"results": results}
def _severity_score(sev: str) -> float:
    mapping = {"None": 0.0, "Mild": 1.0, "Moderate": 2.0, "Severe": 3.0}
    return mapping.get(sev, 0.0)
def _evidence_score(ev: str) -> float:
    mapping = {"A": 1.0, "B": 1.2, "C": 1.5, "D": 2.0}
    # Higher means less strong evidence, invert later
    return mapping.get(ev, 2.0)
def _compute_risk(inter: Dict[str, Any]) -> float:
    severity_score = _severity_score(inter.get("severity", "None"))
    evidence_score = _evidence_score(inter.get("evidence", "D"))
    mechanisms = inter.get("mechanism", [])
    mech_sum = sum(MECHANISM_DELTAS.get(m, 0.0) for m in mechanisms)
    severity_weight = WEIGHTS.get("severity", DEFAULT_WEIGHTS["severity"])
    evidence_weight = WEIGHTS.get("evidence", DEFAULT_WEIGHTS["evidence"])
    mechanism_weight = WEIGHTS.get("mechanism", DEFAULT_WEIGHTS["mechanism"])
    if evidence_score:
        evidence_component = (1.0 / evidence_score) * evidence_weight
    else:
        evidence_component = 0.0
    weights_ns = SimpleNamespace(**{**DEFAULT_WEIGHTS, **WEIGHTS})
    mechanisms_ns = SimpleNamespace(**MECHANISM_DELTAS)
    interaction_ns = SimpleNamespace(**{k: v for k, v in inter.items()})
    context = {
        "severity": severity_score,
        "evidence": evidence_score,
        "mech_sum": mech_sum,
        "mechanism_sum": mech_sum,
        "weights": weights_ns,
        "mechanisms": mechanisms_ns,
        "interaction": interaction_ns,
        "evidence_component": evidence_component,
        "severity_component": severity_score * getattr(weights_ns, "severity", severity_weight),
        "mechanism_component": mech_sum * getattr(weights_ns, "mechanism", mechanism_weight),
        "mechanism_count": len(mechanisms),
        "sources_count": len(inter.get("sources", [])),
    }
    try:
        risk_value = float(RISK_FORMULA(**context)) if RISK_FORMULA else float(_default_formula(**context))
    except Exception:
        risk_value = float(_default_formula(**context))
    return round(risk_value, 2)
def _resolve_compound(token: str) -> Optional[Dict[str, Any]]:
    if token in COMPOUNDS:
        comp = COMPOUNDS[token]
        # ensure we got canonical dict (not alias key value)
        return COMPOUNDS.get(comp.get("id"), comp)
    key = _normalise_name(token)
    return COMPOUNDS.get(key)
@app.get("/api/interaction")
def interaction(a: str, b: str):
    """Get interaction details between two compounds by id or name."""
    comp_a = _resolve_compound(a)
    comp_b = _resolve_compound(b)
    if not comp_a:
        raise HTTPException(status_code=404, detail=f"Unknown compound: {a}")
    if not comp_b:
        raise HTTPException(status_code=404, detail=f"Unknown compound: {b}")
    key = (comp_a["id"], comp_b["id"])
    inter = INTERACTIONS.get(key)
    if not inter:
        # Try reverse if not already added
        inter = INTERACTIONS.get((comp_b["id"], comp_a["id"]))
    if not inter:
        raise HTTPException(status_code=404, detail="No interaction found for the given pair")
    risk = _compute_risk(inter)
    payload = {**inter, "a_compound": comp_a, "b_compound": comp_b, "risk": risk}
    return payload
@app.post("/api/stack/check")
def stack_check(req: StackRequest):
    """Check pairwise interactions across a stack of compounds."""
    if not req.items or len(req.items) < 2:
        return {"results": [], "count": 0}
    # Resolve all items
    resolved: List[Dict[str, Any]] = []
    for t in req.items:
        comp = _resolve_compound(t)
        if not comp:
            raise HTTPException(status_code=404, detail=f"Unknown compound: {t}")
        if comp["id"] not in {c.get("id") for c in resolved}:
            resolved.append(comp)
    results: List[Dict[str, Any]] = []
    for i in range(len(resolved)):
        for j in range(i + 1, len(resolved)):
            a = resolved[i]["id"]
            b = resolved[j]["id"]
            inter = INTERACTIONS.get((a, b)) or INTERACTIONS.get((b, a))
            if inter:
                risk = _compute_risk(inter)
                results.append({**inter, "a_compound": resolved[i], "b_compound": resolved[j], "risk": risk})
    return {"results": results, "count": len(results)}

# Export alias for compatibility with test_stack.py
check_stack = stack_check
