"""
Data loading utilities for the SuppTracker backend.

Loads CSV and YAML data files at startup and provides precomputed
data structures for fast access.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import yaml

from synonyms import parse_synonyms

HERE = Path(__file__).parent
DATA = Path(os.environ.get("SUPPTRACKER_DATA_DIR", HERE / "data"))


def load_csv(name: str) -> pd.DataFrame:
    """Load a CSV file from the configured data directory."""
    p = DATA / name
    if not p.exists():
        raise FileNotFoundError(f"Missing data file: {name} in {DATA}")
    return pd.read_csv(p)


def load_yaml(name: str) -> dict:
    """Load a YAML file from the configured data directory."""
    p = DATA / name
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def to_synonyms(s: str) -> List[str]:
    """Parse synonyms using [|,;/] separators; lowercased and distinct."""
    if pd.isna(s) or str(s).strip() == "":
        return []
    return parse_synonyms(str(s))


def load_all_data() -> Dict[str, Any]:
    """
    Load all data files and return a dictionary with precomputed structures.

    Returns a dict with keys:
        boot_error, compounds, interactions, sources, rules,
        interaction_index (dict keyed by normalized pair tuples for O(1) lookup)
    """
    result: Dict[str, Any] = {
        "boot_error": "",
        "compounds": [],
        "interactions": [],
        "sources": {},
        "rules": {},
        "interaction_index": {},
    }

    # Load CSVs
    try:
        compounds_df = load_csv("compounds.csv")
        interactions_df = load_csv("interactions.csv")
        sources_df = load_csv("sources.csv")
    except Exception as e:
        result["boot_error"] = str(e)
        return result

    # Load YAML rules
    try:
        result["rules"] = load_yaml("risk_rules.yaml")
    except Exception as e:
        result["boot_error"] = str(e)
        return result

    # Build compounds list
    for _, row in compounds_df.iterrows():
        result["compounds"].append(
            {
                "id": str(row.get("id", "")),
                "name": str(row.get("name", "")),
                "synonyms": to_synonyms(row.get("synonyms", "")),
                "class": str(row.get("class", "")),
                "route": str(row.get("route", "")),
                "common_dose": str(row.get("common_dose", "")),
                "qt_risk": str(row.get("qt_risk", "")),
                "notes": str(row.get("notes", "")),
            }
        )

    # Build interactions list and O(1) index
    interactions = interactions_df.to_dict(orient="records")
    result["interactions"] = interactions

    index: Dict[tuple, Dict[str, Any]] = {}
    for row in interactions:
        a = str(row.get("compound_a", "")).strip().lower()
        b = str(row.get("compound_b", "")).strip().lower()
        key = (min(a, b), max(a, b))
        if key not in index:
            index[key] = row
    result["interaction_index"] = index

    # Build sources dict
    result["sources"] = {
        str(row["id"]): row.to_dict() for _, row in sources_df.iterrows()
    }

    return result
