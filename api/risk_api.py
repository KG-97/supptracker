from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Optional, Tuple, Callable, Any, Union
from pathlib import Path
import logging
import os
import csv
import re
import yaml
import ast
import json
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
    severity: Literal['None', 'Mild', 'Moderate', 'Severe']
    evidence: Literal['A', 'B', 'C', 'D']
    effect: str
    action: str
    sources: List[str] = Field(default_factory=list)

class StackRequest(BaseModel):
    items: List[str] = Field(..., description="List of compound IDs or names")

logger = logging.getLogger("supptracker")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Paths and data helpers
BASE_DIR: Path = Path(__file__).resolve().parent.parent
# Support both legacy and new env vars, with new one taking precedence
DATA_DIR: Path = Path(
    os.environ.get("SUPPTRACKER_DATA_DIR",
    os.environ.get("SUPPTRACKER_DATA", BASE_DIR / "data"))
).expanduser().resolve()

def get_data_dir(override: Optional[str] = None) -> Path:
    """Return the directory that contains the seed CSV files."""
    if override:
        return Path(override).expanduser().resolve()
    return DATA_DIR

# Global data store
COMPOUNDS: Dict[str, dict] = {}
INTERACTIONS: List[dict] = []

def _normalise_name(name: str) -> str:
    """Normalise compound names for consistent lookups."""
    return re.sub(r'[^a-z0-9]', '', name.lower())

def _normalise_mechanisms(mechanisms_str: str) -> List[str]:
    """Split mechanisms on pipe, comma, and semicolon delimiters and normalize."""
    if not mechanisms_str:
        return []
    # Split on pipe, comma, semicolon and strip whitespace
    tokens = re.split(r'[|,;]+', mechanisms_str)
    return [token.strip() for token in tokens if token.strip()]

def _resolve_compound(identifier: str) -> Optional[dict]:
    """Resolve a compound by ID or name, returning the compound dict if found."""
    # Try direct ID lookup first
    if identifier in COMPOUNDS:
        return COMPOUNDS[identifier]
    
    # Try normalised name lookup
    key = _normalise_name(identifier)
    for compound in COMPOUNDS.values():
        if _normalise_name(compound["name"]) == key:
            return compound
        # Check synonyms
        for synonym in compound.get("synonyms", []):
            if _normalise_name(synonym) == key:
                return compound
    return None

def _compute_risk(interaction: dict) -> float:
    """Compute risk score for an interaction."""
    severity_scores = {"None": 0, "Mild": 1, "Moderate": 2, "Severe": 3}
    evidence_scores = {"A": 3, "B": 2, "C": 1, "D": 0.5}
    
    severity = interaction.get("severity", "None")
    evidence = interaction.get("evidence", "D")
    
    # Base score from severity and evidence
    base_score = severity_scores.get(severity, 0) * evidence_scores.get(evidence, 0.5)
    
    # Mechanism bonus - more mechanisms = higher risk
    mechanism_count = len(interaction.get("mechanism", []))
    mechanism_bonus = min(mechanism_count * 0.2, 1.0)  # Cap at +1.0
    
    return min(base_score + mechanism_bonus, 10.0)  # Cap at 10.0

def _load_compounds(data_dir: Path) -> None:
    """Load compounds from CSV file."""
    global COMPOUNDS
    compounds_path = data_dir / "compounds.csv"
    
    if not compounds_path.exists():
        logger.warning(f"Compounds file not found: {compounds_path}")
        return
    
    try:
        with open(compounds_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Parse synonyms if present
                synonyms = []
                if row.get('synonyms'):
                    try:
                        synonyms = ast.literal_eval(row['synonyms'])
                    except (ValueError, SyntaxError):
                        synonyms = [s.strip() for s in row['synonyms'].split(',')]
                
                compound = {
                    'id': row['id'],
                    'name': row['name'],
                    'synonyms': synonyms,
                    'cls': row.get('cls', ''),
                    'typicalDoseAmount': row.get('typicalDoseAmount', ''),
                    'typicalDoseUnit': row.get('typicalDoseUnit', ''),
                    'route': row.get('route', '')
                }
                COMPOUNDS[row['id']] = compound
        
        logger.info(f"Loaded {len(COMPOUNDS)} compounds")
    except Exception as e:
        logger.error(f"Error loading compounds: {e}")

def _load_interactions(data_dir: Path) -> None:
    """Load interactions from CSV file."""
    global INTERACTIONS
    interactions_path = data_dir / "interactions.csv"
    
    if not interactions_path.exists():
        logger.warning(f"Interactions file not found: {interactions_path}")
        return
    
    try:
        with open(interactions_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Parse mechanism field using the new normalization
                mechanisms = _normalise_mechanisms(row.get('mechanism', ''))
                
                # Parse sources if present
                sources = []
                if row.get('sources'):
                    try:
                        sources = ast.literal_eval(row['sources'])
                    except (ValueError, SyntaxError):
                        sources = [s.strip() for s in row['sources'].split(',')]
                
                interaction = {
                    'id': row['id'],
                    'a': row['a'],
                    'b': row['b'],
                    'bidirectional': row.get('bidirectional', 'true').lower() == 'true',
                    'mechanism': mechanisms,
                    'severity': row.get('severity', 'None'),
                    'evidence': row.get('evidence', 'D'),
                    'effect': row.get('effect', ''),
                    'action': row.get('action', ''),
                    'sources': sources
                }
                INTERACTIONS.append(interaction)
        
        logger.info(f"Loaded {len(INTERACTIONS)} interactions")
    except Exception as e:
        logger.error(f"Error loading interactions: {e}")

def load_data(data_dir: Optional[Path] = None) -> None:
    """Load all data from CSV files."""
    if data_dir is None:
        data_dir = get_data_dir()
    
    logger.info(f"Loading data from: {data_dir}")
    _load_compounds(data_dir)
    _load_interactions(data_dir)

# Load data on startup
load_data()

# Mount static files for SPA
if Path("frontend_dist").exists():
    app.mount("/static", StaticFiles(directory="frontend_dist/static"), name="static")

# API Routes
@app.get("/api/compounds")
def list_compounds():
    """List all available compounds."""
    return list(COMPOUNDS.values())

@app.get("/api/compounds/{compound_id}")
def get_compound(compound_id: str):
    """Get a specific compound by ID."""
    if compound_id not in COMPOUNDS:
        raise HTTPException(status_code=404, detail="Compound not found")
    return COMPOUNDS[compound_id]

@app.get("/api/interactions")
def list_interactions():
    """List all interactions."""
    return INTERACTIONS

@app.get("/api/interaction")
def get_interaction(a: str, b: str):
    """Get interaction details between two compounds by id or name."""
    comp_a = _resolve_compound(a)
    comp_b = _resolve_compound(b)
    
    if not comp_a:
        raise HTTPException(status_code=404, detail=f"Unknown compound: {a}")
    if not comp_b:
        raise HTTPException(status_code=404, detail=f"Unknown compound: {b}")
    
    # Find interaction
    for inter in INTERACTIONS:
        if ((inter["a"] == comp_a["id"] and inter["b"] == comp_b["id"]) or
            (inter.get("bidirectional", False) and 
             inter["a"] == comp_b["id"] and inter["b"] == comp_a["id"])):
            risk = _compute_risk(inter)
            return {**inter, "a_compound": comp_a, "b_compound": comp_b, "risk": risk}
    
    raise HTTPException(status_code=404, detail="No interaction found for the given pair")

@app.post("/api/stack/check")
def check_stack(payload: StackRequest):
    """Check interactions within a stack of compounds."""
    if not payload.items or len(payload.items) < 2:
        return {"results": [], "count": 0}
    
    # Resolve all items
    resolved: List[Dict[str, Any]] = []
    for item in payload.items:
        comp = _resolve_compound(item)
        if not comp:
            raise HTTPException(status_code=404, detail=f"Unknown compound: {item}")
        if comp["id"] not in {c.get("id") for c in resolved}:
            resolved.append(comp)
    
    # Find all pairwise interactions
    results: List[Dict[str, Any]] = []
    for i in range(len(resolved)):
        for j in range(i + 1, len(resolved)):
            a_id = resolved[i]["id"]
            b_id = resolved[j]["id"]
            
            # Find interaction
            for inter in INTERACTIONS:
                if ((inter["a"] == a_id and inter["b"] == b_id) or
                    (inter.get("bidirectional", False) and 
                     inter["a"] == b_id and inter["b"] == a_id)):
                    risk = _compute_risk(inter)
                    results.append({
                        **inter, 
                        "a_compound": resolved[i], 
                        "b_compound": resolved[j], 
                        "risk": risk
                    })
                    break
    
    return {"results": results, "count": len(results)}

# Export alias for compatibility with test_stack.py
stack_check = check_stack

# SPA fallback route - must be last
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str, request: Request):
    """Serve React app for all non-API routes (SPA fallback)."""
    # Skip API routes
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Check if it's a static file request
    static_file_path = Path("frontend_dist") / full_path
    if static_file_path.is_file():
        return FileResponse(static_file_path)
    
    # Serve index.html for all other routes (SPA)
    return FileResponse("frontend_dist/index.html")
