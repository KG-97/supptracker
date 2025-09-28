import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Union
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from api.models import Compound, Interaction, Source

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

# Serve static files from frontend build
app.mount("/static", StaticFiles(directory="frontend_dist/assets"), name="static")

# Global data stores
COMPOUNDS: Dict[str, Dict[str, Any]] = {}
INTERACTIONS: List[Dict[str, Any]] = []
SOURCES: Dict[str, Dict[str, Any]] = {}

# Data loading functions
def load_data():
    """Load all data files."""
    global COMPOUNDS, INTERACTIONS, SOURCES
    
    # Determine data directory
    data_dir = Path(os.getenv("SUPPTRACKER_DATA_DIR", "data"))
    
    # Load compounds
    compounds_file = data_dir / "compounds.json"
    if compounds_file.exists():
        try:
            with open(compounds_file) as f:
                compounds_data = json.load(f)
            COMPOUNDS = {comp["id"]: comp for comp in compounds_data}
            logger.info(f"Loaded {len(COMPOUNDS)} compounds")
        except Exception as e:
            logger.error(f"Failed to load compounds: {e}")
    else:
        logger.warning(f"Compounds file not found: {compounds_file}")
    
    # Load interactions
    interactions_file = data_dir / "interactions.json"
    if interactions_file.exists():
        try:
            with open(interactions_file) as f:
                INTERACTIONS.clear()
                INTERACTIONS.extend(json.load(f))
            logger.info(f"Loaded {len(INTERACTIONS)} interactions")
        except Exception as e:
            logger.error(f"Failed to load interactions: {e}")
    else:
        logger.warning(f"Interactions file not found: {interactions_file}")
    
    # Load sources
    sources_file = data_dir / "sources.json"
    if sources_file.exists():
        try:
            with open(sources_file) as f:
                sources_data = json.load(f)
            SOURCES = {src["id"]: src for src in sources_data}
            logger.info(f"Loaded {len(SOURCES)} sources")
        except Exception as e:
            logger.error(f"Failed to load sources: {e}")
    else:
        logger.warning(f"Sources file not found: {sources_file}")

# Load data on startup
load_data()

# Helper functions
def resolve_compound(identifier: str) -> Optional[str]:
    """Resolve compound by ID or name."""
    if identifier in COMPOUNDS:
        return identifier
    
    # Search by name and aliases
    identifier_lower = identifier.lower()
    for comp_id, comp in COMPOUNDS.items():
        if comp.get("name", "").lower() == identifier_lower:
            return comp_id
        
        # Check aliases
        aliases = comp.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias.lower() == identifier_lower:
                    return comp_id
    
    return None

def compute_risk(interaction: Dict[str, Any]) -> float:
    """Compute numerical risk score from interaction data."""
    severity_map = {"low": 2.0, "moderate": 5.0, "high": 8.0}
    evidence_map = {"theoretical": 0.5, "case_reports": 1.0, "studies": 1.5}
    
    severity_score = severity_map.get(interaction.get("severity", "moderate"), 5.0)
    evidence_score = evidence_map.get(interaction.get("evidence", "studies"), 1.0)
    
    return min(10.0, severity_score * evidence_score)

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

@app.get("/api/compounds/{compound_id}")
def get_compound(compound_id: str):
    """Get specific compound by ID."""
    if compound_id not in COMPOUNDS:
        raise HTTPException(status_code=404, detail="Compound not found")
    return COMPOUNDS[compound_id]

@app.get("/api/search")
def search(query: str, limit: int = 10):
    """Search compounds by name or alias."""
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is required")
    
    query_lower = query.lower()
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
    static_file_path = Path("frontend_dist") / full_path
    if static_file_path.is_file():
        return FileResponse(static_file_path)
    
    # Serve index.html for all other routes (SPA)
    return FileResponse("frontend_dist/index.html")
