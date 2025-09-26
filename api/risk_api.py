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

def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        logger.warning("Data file missing: %s", path)
        return []
    try:
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Failed to read CSV %s: %s", path, exc)
        return []

def load_compounds(data_dir: Optional[Path] = None) -> Dict[str, dict]:
    compounds: Dict[str, dict] = {}
    base_dir = Path(data_dir) if data_dir is not None else get_data_dir()
    path = base_dir / "compounds.csv"
    for row in _read_csv_rows(path):
        raw_synonyms = row.get("synonyms") or ""
        if raw_synonyms:
            parts = re.split(r"[\|,;]", raw_synonyms)
            synonyms = [s.strip() for s in parts if s.strip()]
        else:
            synonyms = []
        cid = (row.get("id") or "").strip()
        name = (row.get("name") or "").strip()
        if not cid or not name:
            continue
        compounds[cid] = {
            "id": cid,
            "name": name,
            "synonyms": synonyms,
            "class": row.get("class") or None,
            "typicalDoseAmount": row.get("typicalDoseAmount") or None,
            "typicalDoseUnit": row.get("typicalDoseUnit") or None,
            "route": row.get("route") or None,
        }
    return compounds

def load_interactions(data_dir: Optional[Path] = None) -> List[dict]:
    interactions: List[dict] = []
    base_dir = Path(data_dir) if data_dir is not None else get_data_dir()
    path = base_dir / "interactions.csv"
    for row in _read_csv_rows(path):
        interaction_id = (row.get("id") or "").strip()
        a = (row.get("a") or "").strip()
        b = (row.get("b") or "").strip()
        if not interaction_id or not a or not b:
            continue
        mechanisms = [m.strip() for m in (row.get("mechanism") or "").split("|") if m.strip()]
        sources = [s.strip() for s in (row.get("sources") or "").split("|") if s.strip()]
        raw_bidirectional = str(row.get("bidirectional", "")).strip().lower()
        bidirectional = True
        if raw_bidirectional:
            bidirectional = raw_bidirectional in {"true", "1", "yes", "y"}
        interactions.append({
            "id": interaction_id,
            "a": a,
            "b": b,
            "bidirectional": bidirectional,
            "mechanism": mechanisms,
            "severity": row.get("severity", "None"),
            "evidence": row.get("evidence", "D"),
            "effect": row.get("effect", ""),
            "action": row.get("action", ""),
            "sources": sources,
        })
    return interactions

def load_sources(data_dir: Optional[Path] = None) -> Dict[str, dict]:
    sources: Dict[str, dict] = {}
    base_dir = Path(data_dir) if data_dir is not None else get_data_dir()
    path = base_dir / "sources.csv"
    for row in _read_csv_rows(path):
        sid = (row.get("id") or "").strip()
        if sid:
            sources[sid] = row
    return sources

def load_all_data(data_dir: Optional[str] = None) -> None:
    """Populate the in-memory data stores from CSV files."""
    data_path = get_data_dir(data_dir)
    logger.info("Loading seed data from %s", data_path)
    global COMPOUNDS, INTERACTIONS, SOURCES, DATA_DIR
    COMPOUNDS = load_compounds(data_path)
    INTERACTIONS = load_interactions(data_path)
    SOURCES = load_sources(data_path)
    DATA_DIR = data_path
    logger.info(
        "Loaded %d compounds, %d interactions, %d sources",
        len(COMPOUNDS),
        len(INTERACTIONS),
        len(SOURCES),
    )

COMPOUNDS: Dict[str, dict] = {}
INTERACTIONS: List[dict] = []
SOURCES: Dict[str, dict] = {}

load_all_data()

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

RULES_PATH = os.environ.get(
    "RISK_RULES_PATH",
    os.path.join(os.path.dirname(__file__), "rules.yaml"),
)

DEFAULT_FORMULA_SOURCE = "severity * weights.severity + evidence_component + mech_sum * weights.mechanism"

def _default_formula(**context: Any) -> float:
    """Fallback risk calculation mirroring the legacy logic."""
    weights = context.get("weights") or SimpleNamespace(**DEFAULT_WEIGHTS)
    severity_component = context.get("severity", 0.0) * getattr(weights, "severity", DEFAULT_WEIGHTS["severity"])
    mech_component = context.get("mech_sum", 0.0) * getattr(weights, "mechanism", DEFAULT_WEIGHTS["mechanism"])
    return severity_component + context.get("evidence_component", 0.0) + mech_component

SAFE_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Num,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.Constant,
    ast.Attribute,
    ast.Compare,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Eq,
    ast.NotEq,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.IfExp,
    ast.Call,
    ast.Tuple,
    ast.List,
    ast.Subscript,
)

SAFE_FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
}

def compile_formula(expr: Optional[str]) -> Tuple[Callable[..., float], str]:
    """Compile a risk score formula into a safe callable."""
    if not expr or not str(expr).strip():
        return _default_formula, DEFAULT_FORMULA_SOURCE
    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError:
        return _default_formula, DEFAULT_FORMULA_SOURCE
    for node in ast.walk(tree):
        if not isinstance(node, SAFE_AST_NODES):
            return _default_formula, DEFAULT_FORMULA_SOURCE
        if isinstance(node, ast.Call):
            func = node.func
            if not isinstance(func, ast.Name) or func.id not in SAFE_FUNCTIONS:
                return _default_formula, DEFAULT_FORMULA_SOURCE
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return _default_formula, DEFAULT_FORMULA_SOURCE
    code = compile(tree, "<risk_formula>", "eval")
    def _formula(**context: Any) -> float:
        env: Dict[str, Any] = {**SAFE_FUNCTIONS, **context}
        return float(eval(code, {"__builtins__": {}}, env))
    return _formula, str(expr)

def load_rules(path: Optional[str] = None) -> Tuple[
    Dict[str, float], Dict[str, float], Dict[str, int], Dict[str, int], Callable[..., float], str
]:
    """Load risk model parameters from YAML configuration."""
    path = path or RULES_PATH
    mechanisms = DEFAULT_MECHANISM_DELTAS.copy()
    weights = DEFAULT_WEIGHTS.copy()
    severity_map = DEFAULT_SEVERITY_MAP.copy()
    evidence_map = DEFAULT_EVIDENCE_MAP.copy()
    if not path:
        return mechanisms, weights, severity_map, evidence_map, _default_formula, DEFAULT_FORMULA_SOURCE
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return mechanisms, weights, severity_map, evidence_map, _default_formula, DEFAULT_FORMULA_SOURCE
    except (yaml.YAMLError, OSError):
        return mechanisms, weights, severity_map, evidence_map, _default_formula, DEFAULT_FORMULA_SOURCE
    if not isinstance(data, dict):
        return mechanisms, weights, severity_map, evidence_map, _default_formula, DEFAULT_FORMULA_SOURCE
    mechanisms_cfg = data.get("mechanisms")
    if isinstance(mechanisms_cfg, dict):
        for name, entry in mechanisms_cfg.items():
            delta = entry.get("delta") if isinstance(entry, dict) else entry
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
    formula_callable, formula_source = compile_formula(data.get("formula"))
    return mechanisms, weights, severity_map, evidence_map, formula_callable, formula_source

def apply_rules(path: Optional[str] = None) -> None:
    """Apply rule configuration from the provided path or defaults."""
    global MECHANISM_DELTAS, WEIGHTS, SEVERITY_MAP, EVIDENCE_MAP, RISK_FORMULA, RISK_FORMULA_SOURCE
    (
        MECHANISM_DELTAS,
        WEIGHTS,
        SEVERITY_MAP,
        EVIDENCE_MAP,
        RISK_FORMULA,
        RISK_FORMULA_SOURCE,
    ) = load_rules(path)

RISK_FORMULA: Callable[..., float] = _default_formula
RISK_FORMULA_SOURCE: str = DEFAULT_FORMULA_SOURCE

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
        "mechanism_count": len(inter.get("mechanism", [])),
        "sources_count": len(inter.get("sources", [])),
    }
    try:
        risk_value = float(RISK_FORMULA(**context))
    except Exception:
        risk_value = float(_default_formula(**context))
    return round(risk_value, 2)

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
    """Get interaction details between two compounds by id or name.""