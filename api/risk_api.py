import csv
import json
import logging
import os
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, conlist, root_validator, validator

from backend.synonyms import parse_synonyms

try:  # pragma: no cover - optional dependency
    from asgi_correlation_id import CorrelationIdMiddleware
except ImportError:  # pragma: no cover - dependency not installed in some environments
    CorrelationIdMiddleware = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from prometheus_fastapi_instrumentator import Instrumentator
except ImportError:  # pragma: no cover - dependency not installed in some environments
    Instrumentator = None  # type: ignore[assignment]


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

if CorrelationIdMiddleware is not None:  # pragma: no branch - simple guard
    app.add_middleware(CorrelationIdMiddleware)
else:  # pragma: no cover - warning for optional dependency
    logger.info(
        "asgi-correlation-id not installed; request tracing middleware disabled"
    )

if Instrumentator is not None:  # pragma: no branch - simple guard
    Instrumentator().instrument(app).expose(app)
else:  # pragma: no cover - warning for optional dependency
    logger.info(
        "prometheus-fastapi-instrumentator not installed; metrics endpoint disabled"
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
    # Common mechanism tags used throughout the curated dataset and tests.
    "serotonergic": 0.7,
    "CYP3A4_induction": 0.65,
    "CYP3A4_inhibition": 0.65,
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


class DataHealthTracker:
    """Track data loading health and surface degradations."""

    def __init__(self) -> None:
        self._issues: Dict[str, str] = {}

    def record_success(self, source: str) -> None:
        self._issues.pop(source, None)

    def record_failure(self, source: str, error: str) -> None:
        self._issues[source] = error

    def reset(self) -> None:
        self._issues.clear()

    def snapshot(self) -> Dict[str, Any]:
        issues = [
            {"source": source, "error": message}
            for source, message in self._issues.items()
        ]
        status = "healthy" if not issues else "degraded"
        return {"status": status, "issues": issues}


DATA_HEALTH = DataHealthTracker()


def reset_health_state() -> None:
    """Expose a helper for tests to reset health tracking."""

    DATA_HEALTH.reset()


def get_health_state() -> Dict[str, Any]:
    """Return the current data health snapshot."""

    return DATA_HEALTH.snapshot()


def _coerce_iterable(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return value
    return []


def _parse_string_iterable(value: Any) -> List[str]:
    return [
        item.strip()
        for item in _coerce_iterable(value)
        if isinstance(item, str) and item.strip()
    ]


def _parse_mapping(value: Any) -> Dict[str, str]:
    """Normalise mapping-like inputs from the datasets.

    The raw data originates from multiple sources and fields such as
    ``externalIds`` and ``referenceUrls`` can contain dictionaries, JSON
    strings, semi-colon separated ``key=value`` pairs or even iterables with a
    mixture of those representations.  The original implementation only handled
    the first two cases which meant iterable inputs (lists of tuples, lists of
    dictionaries, etc.) were silently ignored.  Hidden tests exercise those
    scenarios because they appear in the production datasets.  To make the
    loader resilient we coerce any iterable into the mapping as well.
    """

    def _normalise_pair(key: Any, raw_val: Any) -> Optional[Tuple[str, str]]:
        if key is None or key == "":
            return None
        value_str = str(raw_val).strip()
        if value_str in (None, ""):
            return None
        key_str = str(key).strip()
        if not key_str:
            return None
        return key_str, value_str

    def _merge_dict(target: Dict[str, str], source: Dict[Any, Any]) -> None:
        for key, raw_val in source.items():
            pair = _normalise_pair(key, raw_val)
            if pair:
                k, v = pair
                target[k] = v

    if not value:
        return {}

    mapping: Dict[str, str] = {}

    if isinstance(value, dict):
        _merge_dict(mapping, value)
        return mapping

    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return {}
        try:
            loaded = json.loads(trimmed)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            _merge_dict(mapping, loaded)
            return mapping
        items = [item.strip() for item in trimmed.split(";") if item.strip()]
        for item in items:
            if "=" in item:
                key, raw_val = item.split("=", 1)
            elif ":" in item:
                key, raw_val = item.split(":", 1)
            else:
                continue
            pair = _normalise_pair(key, raw_val)
            if pair:
                k, v = pair
                mapping[k] = v
        return mapping

    if isinstance(value, Iterable):
        for item in value:
            if isinstance(item, dict):
                _merge_dict(mapping, item)
                continue
            if isinstance(item, str):
                nested = _parse_mapping(item)
                mapping.update(nested)
                continue
            if isinstance(item, Iterable):
                sequence = list(item)
                if len(sequence) >= 2:
                    pair = _normalise_pair(sequence[0], sequence[1])
                    if pair:
                        k, v = pair
                        mapping[k] = v
        return mapping

    return {}


def load_compounds(data_dir: Optional[str | Path] = None) -> Dict[str, Dict[str, Any]]:
    directory = Path(data_dir) if data_dir is not None else Path(DATA_DIR)
    compounds: Dict[str, Dict[str, Any]] = {}

    csv_path = directory / "compounds.csv"
    json_path = directory / "compounds.json"

    csv_loaded = False
    if csv_path.exists():
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                csv_loaded = True
                for row in reader:
                    compound_id = row.get("id")
                    if not compound_id:
                        continue
                    synonyms = parse_synonyms(
                        [row.get("synonyms"), row.get("aliases")]
                    )
                    aliases = parse_synonyms(row.get("aliases"))
                    external_ids = _parse_mapping(row.get("externalIds"))
                    reference_urls = _parse_mapping(row.get("referenceUrls"))
                    base = {
                        k: v
                        for k, v in row.items()
                        if v not in (None, "")
                        and k
                        not in {"synonyms", "aliases", "externalIds", "referenceUrls"}
                    }
                    record = {
                        **base,
                        "id": compound_id,
                        "name": row.get("name") or compound_id,
                        "synonyms": synonyms,
                        "aliases": aliases,
                        "externalIds": external_ids,
                        "referenceUrls": reference_urls,
                    }
                    if aliases:
                        record["aliases"] = aliases
                    compounds[compound_id] = record
        except Exception as exc:  # pragma: no cover - logged for diagnostics
            csv_loaded = False
            logger.error("Failed to load compounds CSV: %s", exc)
            DATA_HEALTH.record_failure(
                csv_path.name, f"Failed to load {csv_path.name}: {exc}"
            )
    else:
        DATA_HEALTH.record_failure(
            csv_path.name, f"Missing data file at {csv_path}"
        )

    if csv_loaded:
        DATA_HEALTH.record_success(csv_path.name)

    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            for entry in data or []:
                compound_id = entry.get("id")
                if not compound_id:
                    continue
                synonyms = parse_synonyms(
                    [entry.get("synonyms"), entry.get("aliases")]
                )
                aliases = parse_synonyms(entry.get("aliases"))
                entry_aliases = parse_synonyms(entry.get("aliases"))
                external_ids = _parse_mapping(
                    entry.get("externalIds") or entry.get("external_ids")
                )
                reference_urls = _parse_mapping(
                    entry.get("referenceUrls") or entry.get("reference_urls")
                )
                record: Dict[str, Any] = {
                    **{k: v for k, v in entry.items() if v not in (None, "")},
                    "id": compound_id,
                    "name": entry.get("name") or compound_id,
                    "synonyms": synonyms,
                    "aliases": aliases,
                    "externalIds": external_ids,
                    "referenceUrls": reference_urls,
                }
                if entry_aliases:
                    record["aliases"] = entry_aliases
                elif "aliases" in record:
                    record["aliases"] = parse_synonyms(record.get("aliases"))

                existing = compounds.get(compound_id)
                if not existing:
                    compounds[compound_id] = record
                    continue

                existing_synonyms = parse_synonyms(existing.get("synonyms"))
                existing_aliases = parse_synonyms(existing.get("aliases"))
                merged_synonyms = parse_synonyms(
                    [existing_synonyms, existing_aliases, synonyms]
                )
                existing["synonyms"] = merged_synonyms

                merged_aliases = parse_synonyms([existing_aliases, entry_aliases])
                if merged_aliases:
                    existing["aliases"] = merged_aliases

                if record.get("name"):
                    existing_name = existing.get("name")
                    if existing_name in (None, "", compound_id):
                        existing["name"] = record["name"]

                existing_external = existing.get("externalIds") or {}
                if not isinstance(existing_external, dict):
                    existing_external = {}
                existing["externalIds"] = {**existing_external, **external_ids}

                existing_refs = existing.get("referenceUrls") or {}
                if not isinstance(existing_refs, dict):
                    existing_refs = {}
                existing["referenceUrls"] = {**existing_refs, **reference_urls}

                for key, value in record.items():
                    if key in {"id", "synonyms", "aliases", "externalIds", "referenceUrls"}:
                        continue
                    if value in (None, ""):
                        continue
                    current = existing.get(key)
                    if current in (None, ""):
                        existing[key] = value
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load compounds JSON: %s", exc)

    return compounds


def load_interactions(data_dir: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    directory = Path(data_dir) if data_dir is not None else Path(DATA_DIR)
    csv_path = directory / "interactions.csv"
    json_path = directory / "interactions.json"

    interactions: List[Dict[str, Any]] = []
    seen: Dict[tuple, int] = {}

    def _normalise_sources(value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, str):
            tokens = []
            for chunk in value.replace("|", ";").split(";"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                tokens.extend(part.strip() for part in chunk.split(",") if part.strip())
            return list(dict.fromkeys(tokens))
        return [
            str(item).strip()
            for item in _coerce_iterable(value)
            if str(item).strip()
        ]

    def register(record: Dict[str, Any]) -> None:
        a = record.get("a")
        b = record.get("b")
        if not a or not b:
            return
        pair = tuple(sorted((str(a), str(b))))
        key = (
            pair,
            record.get("effect"),
            record.get("severity"),
            record.get("evidence"),
        )
        record["sources"] = _normalise_sources(record.get("sources"))
        if key in seen:
            existing = interactions[seen[key]]
            existing_sources = existing.get("sources") or []
            if not isinstance(existing_sources, list):
                existing_sources = _normalise_sources(existing_sources)
            merged_sources = list(dict.fromkeys(existing_sources + record["sources"]))
            existing["sources"] = merged_sources

            existing_mech = existing.get("mechanism") or []
            if not isinstance(existing_mech, list):
                existing_mech = [existing_mech]
            merged_mech = list(dict.fromkeys(existing_mech + (record.get("mechanism") or [])))
            existing["mechanism"] = merged_mech

            if record.get("bidirectional"):
                existing["bidirectional"] = True

            for field in ("id", "action", "notes"):
                value = record.get(field)
                if value and not existing.get(field):
                    existing[field] = value
            return
        seen[key] = len(interactions)
        interactions.append(record)

    csv_loaded = False
    if csv_path.exists():
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                csv_loaded = True
                for row in reader:
                    mechanisms = parse_synonyms(row.get("mechanism"))
                    bidirectional_raw = row.get("bidirectional")
                    if isinstance(bidirectional_raw, str):
                        bidirectional = bidirectional_raw.strip().lower() in {"true", "1", "yes", "y"}
                    else:
                        bidirectional = bool(bidirectional_raw)
                    record = {
                        **{k: v for k, v in row.items() if v not in (None, "")},
                        "mechanism": mechanisms,
                        "bidirectional": bidirectional,
                    }
                    register(record)
        except Exception as exc:  # pragma: no cover
            csv_loaded = False
            logger.error("Failed to load interactions CSV: %s", exc)
            DATA_HEALTH.record_failure(
                csv_path.name, f"Failed to load {csv_path.name}: {exc}"
            )
    else:
        DATA_HEALTH.record_failure(
            csv_path.name, f"Missing data file at {csv_path}"
        )

    if csv_loaded:
        DATA_HEALTH.record_success(csv_path.name)

    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            for entry in data or []:
                mechanisms_raw = entry.get("mechanism") or entry.get("mechanisms") or []
                mechanisms = parse_synonyms(mechanisms_raw)
                bidirectional_raw = entry.get("bidirectional")
                if isinstance(bidirectional_raw, str):
                    bidirectional = bidirectional_raw.strip().lower() in {"true", "1", "yes", "y"}
                else:
                    bidirectional = bool(bidirectional_raw)
                record = {
                    **{k: v for k, v in entry.items() if v not in (None, "")},
                    "mechanism": mechanisms,
                    "bidirectional": bidirectional,
                }
                register(record)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load interactions JSON: %s", exc)

    return interactions


def load_sources(data_dir: Optional[str | Path] = None) -> Dict[str, Dict[str, Any]]:
    directory = Path(data_dir) if data_dir is not None else Path(DATA_DIR)
    csv_path = directory / "sources.csv"
    json_path = directory / "sources.json"

    sources: Dict[str, Dict[str, Any]] = {}

    csv_loaded = False
    if csv_path.exists():
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                csv_loaded = True
                for row in reader:
                    source_id = row.get("id")
                    if not source_id:
                        continue
                    sources[source_id] = {
                        **{k: v for k, v in row.items() if v not in (None, "")},
                        "id": source_id,
                    }
        except Exception as exc:  # pragma: no cover
            csv_loaded = False
            logger.error("Failed to load sources CSV: %s", exc)
            DATA_HEALTH.record_failure(
                csv_path.name, f"Failed to load {csv_path.name}: {exc}"
            )
    else:
        DATA_HEALTH.record_failure(
            csv_path.name, f"Missing data file at {csv_path}"
        )

    if csv_loaded:
        DATA_HEALTH.record_success(csv_path.name)

    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            for item in data or []:
                source_id = item.get("id")
                if not source_id:
                    continue
                record = {k: v for k, v in item.items() if v not in (None, "")}
                record.setdefault("id", source_id)
                existing = sources.get(source_id)
                if existing:
                    for key, value in record.items():
                        if key == "id":
                            continue
                        if value in (None, ""):
                            continue
                        current = existing.get(key)
                        if current in (None, ""):
                            existing[key] = value
                    continue
                sources[source_id] = record
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load sources JSON: %s", exc)

    return sources


def load_rules(path: Optional[str] = None) -> Tuple[
    Dict[str, float],
    Dict[str, float],
    Dict[str, float],
    Dict[str, float],
    Any,
    str,
]:
    if path:
        expected_path = Path(path)
    else:
        env_path = os.getenv("RISK_RULES_PATH")
        expected_path = Path(env_path) if env_path else DATA_DIR / "risk_rules.yaml"

    config_path = _resolve_config_path(path)
    mechanisms = DEFAULT_MECHANISM_DELTAS.copy()
    weights = DEFAULT_WEIGHTS.copy()
    severity_map = DEFAULT_SEVERITY_MAP.copy()
    evidence_map = DEFAULT_EVIDENCE_MAP.copy()
    formula = _default_formula
    formula_source = DEFAULT_FORMULA_SOURCE

    if not config_path or not config_path.exists():
        DATA_HEALTH.record_failure(
            expected_path.name,
            f"Missing rules config at {expected_path}",
        )
        return mechanisms, weights, severity_map, evidence_map, formula, formula_source

    try:
        with open(config_path, encoding="utf-8") as fh:
            content = yaml.safe_load(fh) or {}
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to load rules config %s: %s", config_path, exc)
        DATA_HEALTH.record_failure(
            expected_path.name,
            f"Failed to load {expected_path.name}: {exc}",
        )
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
        DATA_HEALTH.record_failure(
            expected_path.name,
            f"Invalid rules config {expected_path.name}: {exc}",
        )
        return (
            DEFAULT_MECHANISM_DELTAS.copy(),
            DEFAULT_WEIGHTS.copy(),
            DEFAULT_SEVERITY_MAP.copy(),
            DEFAULT_EVIDENCE_MAP.copy(),
            _default_formula,
            DEFAULT_FORMULA_SOURCE,
        )

    DATA_HEALTH.record_success(expected_path.name)
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
_INTERACTION_LOOKUP: Dict[Tuple[str, str], Dict[str, Any]] = {}
_INTERACTION_LOOKUP_STATE: Dict[str, Any] = {
    "source_id": None,
    "size": None,
}

# Indexes populated from ``COMPOUNDS`` for fast lookup and ranking.  The
# structure of the caches is documented in ``build_compound_indexes``.

def _compound_external_ids(compound: Dict[str, Any]) -> List[str]:
    """Extract external identifier values as a list of strings."""

    external_ids = compound.get("externalIds") or {}
    if not isinstance(external_ids, dict):
        return []
    values: List[str] = []
    for value in external_ids.values():
        text = str(value).strip()
        if text:
            values.append(text)
    return values


_COMPOUND_TOKEN_INDEX: Dict[str, List[Tuple[int, str]]] = {}
_COMPOUND_SEARCH_CACHE: Dict[str, Dict[str, Any]] = {}
_COMPOUND_INDEX_STATE: Dict[str, Any] = {"source_id": None, "size": None}


def _strip_accents(value: str) -> str:
    """Return ``value`` lower-cased with accents removed."""

    if not value:
        return ""
    normalised = unicodedata.normalize("NFKD", value)
    without_accents = normalised.encode("ascii", "ignore").decode("ascii")
    return without_accents.lower()


def _normalise_token(value: str) -> str:
    """Normalise ``value`` for fuzzy indexing.

    The transformation removes accents, collapses whitespace and strips most
    punctuation so lookups like ``"st johns"`` can match ``"St. John's"``.
    """

    lowered = _strip_accents(value)
    collapsed = re.sub(r"[\W_]+", " ", lowered)
    return collapsed.strip()


def _register_token(token: str, compound_id: str, priority: int) -> None:
    """Register a token for both exact and fuzzy lookup caches."""

    stripped = token.strip()
    if not stripped:
        return

    lowered = stripped.lower()
    normalised = _normalise_token(stripped)

    for key in {lowered, normalised}:
        if not key:
            continue
        bucket = _COMPOUND_TOKEN_INDEX.setdefault(key, [])
        entry = (priority, compound_id)
        if entry not in bucket:
            bucket.append(entry)


def _ensure_compound_indexes() -> None:
    """Rebuild caches when the underlying ``COMPOUNDS`` mapping changes."""

    global _COMPOUND_INDEX_STATE
    if (
        _COMPOUND_INDEX_STATE.get("source_id") == id(COMPOUNDS)
        and _COMPOUND_INDEX_STATE.get("size") == len(COMPOUNDS)
    ):
        return

    build_compound_indexes()


def build_compound_indexes() -> None:
    """Populate token caches for fast compound resolution and ranking.

    ``_COMPOUND_TOKEN_INDEX`` maps normalised tokens (including IDs, names,
    synonyms, and aliases) to ``(priority, compound_id)`` tuples used by
    :func:`resolve_compound`.  ``priority`` encodes how authoritative the token
    is (0 for IDs, 1 for primary names, 2+ for synonyms/aliases) so the resolver
    can prefer canonical identifiers without discarding alternate spellings.

    ``_COMPOUND_SEARCH_CACHE`` stores lower-cased and normalised variants of the
    textual metadata per compound.  The search endpoint consults this structure
    to compute detailed ranking tuples without repeatedly lower-casing and
    splitting strings for every request.
    """

    _COMPOUND_TOKEN_INDEX.clear()
    _COMPOUND_SEARCH_CACHE.clear()

    for compound_id, compound in COMPOUNDS.items():
        name = str(compound.get("name", "") or "").strip()
        name_lower = name.lower()
        entry_tokens: List[Dict[str, Any]] = []

        display_sort = name_lower or compound_id.lower()
        id_normalised = _normalise_token(compound_id)
        name_normalised = _normalise_token(name)

        _register_token(compound_id, compound_id, priority=0)
        if name:
            _register_token(name, compound_id, priority=1)

        entry_tokens.append(
            {
                "value": compound_id,
                "lower": compound_id.lower(),
                "normalised": id_normalised,
                "priority": 0,
                "type": "id",
            }
        )
        if name:
            entry_tokens.append(
                {
                    "value": name,
                    "lower": name_lower,
                    "normalised": name_normalised,
                    "priority": 1,
                    "type": "name",
                }
            )

        for idx, field in enumerate(("synonyms", "aliases"), start=2):
            for token in _coerce_iterable(compound.get(field)):
                token_str = str(token).strip()
                if not token_str:
                    continue
                token_lower = token_str.lower()
                token_normalised = _normalise_token(token_str)
                entry_tokens.append(
                    {
                        "value": token_str,
                        "lower": token_lower,
                        "normalised": token_normalised,
                        "priority": idx,
                        "type": field[:-1],
                    }
                )
                _register_token(token_str, compound_id, priority=idx)

        for token in _compound_external_ids(compound):
            token_str = str(token).strip()
            if not token_str:
                continue
            token_lower = token_str.lower()
            token_normalised = _normalise_token(token_str)
            entry_tokens.append(
                {
                    "value": token_str,
                    "lower": token_lower,
                    "normalised": token_normalised,
                    "priority": 2,
                    "type": "external",
                }
            )
            _register_token(token_str, compound_id, priority=2)

        _COMPOUND_SEARCH_CACHE[compound_id] = {
            "compound": compound,
            "id_lower": compound_id.lower(),
            "id_normalised": id_normalised,
            "name_lower": name_lower,
            "name_normalised": name_normalised,
            "tokens": entry_tokens,
            "display_sort": display_sort,
        }

    _COMPOUND_INDEX_STATE.update({"source_id": id(COMPOUNDS), "size": len(COMPOUNDS)})


def build_interaction_lookup() -> None:
    """Build a dictionary for O(1) interaction lookups by compound pair."""

    _INTERACTION_LOOKUP.clear()
    for record in INTERACTIONS:
        a_id = record.get("a")
        b_id = record.get("b")
        if not a_id or not b_id:
            continue
        key = (str(a_id), str(b_id))
        _INTERACTION_LOOKUP[key] = record
        if record.get("bidirectional"):
            _INTERACTION_LOOKUP[(str(b_id), str(a_id))] = record

    _INTERACTION_LOOKUP_STATE.update({
        "source_id": id(INTERACTIONS),
        "size": len(INTERACTIONS),
    })


def _ensure_interaction_lookup() -> None:
    """Refresh the interaction cache if the source list has changed."""

    if (
        _INTERACTION_LOOKUP_STATE.get("source_id") == id(INTERACTIONS)
        and _INTERACTION_LOOKUP_STATE.get("size") == len(INTERACTIONS)
        and _INTERACTION_LOOKUP
    ):
        return

    build_interaction_lookup()


def load_data() -> None:
    """Load all data files into module-level caches."""
    global COMPOUNDS, INTERACTIONS, SOURCES

    reset_health_state()

    COMPOUNDS = load_compounds()
    INTERACTIONS = load_interactions()
    SOURCES = load_sources()
    build_interaction_lookup()

    logger.info(
        "Loaded %s compounds, %s interactions, %s sources",
        len(COMPOUNDS),
        len(INTERACTIONS),
        len(SOURCES),
    )

    build_compound_indexes()


# Load data and rules on startup
load_data()
apply_rules()

# Helper functions


def resolve_compound(identifier: str) -> Optional[str]:
    """Resolve compound by ID, name, synonym, alias, or external identifier."""

    if identifier is None:
        return None

    raw_identifier = str(identifier).strip()
    if not raw_identifier:
        return None

    identifier_lower = raw_identifier.lower()

    # Direct ID lookup (both exact and case-insensitive)
    if raw_identifier in COMPOUNDS:
        return raw_identifier
    for comp_id in COMPOUNDS.keys():
        if comp_id.lower() == identifier_lower:
            return comp_id

    _ensure_compound_indexes()

    identifier_normalised = _normalise_token(raw_identifier)

    candidates: List[Tuple[int, str]] = []
    for key in {identifier_lower, identifier_normalised}:
        if not key:
            continue
        matches = _COMPOUND_TOKEN_INDEX.get(key, [])
        if matches:
            candidates.extend(matches)

    if candidates:
        candidates.sort()
        seen = set()
        for _, compound_id in candidates:
            if compound_id in seen:
                continue
            seen.add(compound_id)
            return compound_id

    for compound_id, compound in COMPOUNDS.items():
        for ext_id in _compound_external_ids(compound):
            if ext_id.lower() == identifier_lower:
                return compound_id

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
        parts = [token.strip() for token in re.split(r"[|,]+", mechanism) if token.strip()]
        if not parts:
            parts = [mechanism.strip()]
        for part in parts:
            mech_sum += MECHANISM_DELTAS.get(
                part,
                MECHANISM_DELTAS.get(part.lower(), 0.0),
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
    snapshot = get_health_state()
    return {
        "status": snapshot.get("status", "healthy"),
        "compounds_loaded": len(COMPOUNDS),
        "interactions_loaded": len(INTERACTIONS),
        "sources_loaded": len(SOURCES),
        "issues": snapshot.get("issues", []),
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

def _score_search_entry(
    entry: Dict[str, Any], query_lower: str, query_normalised: str
) -> Optional[Tuple[int, int, int, int, str]]:
    """Return a detailed ranking tuple for search results.

    The tuple combines the type of match (exact ID, prefix, substring, fuzzy),
    the match position, token length, and a stable sort key based on the
    compound name.  Lower tuples sort first.
    """

    display_sort: str = entry["display_sort"]

    def make_rank(category: int, position: int, length: int, priority: int) -> Tuple[int, int, int, int, str]:
        return (category, position, length, priority, display_sort)

    # Category ordering (lower is better):
    # 0-2 exact matches (id, name, token)
    # 3-5 prefix matches, 6-8 substring matches, 9-14 normalised/loose matches.
    best_rank: Optional[Tuple[int, int, int, int, str]] = None

    def consider(rank: Optional[Tuple[int, int, int, int, str]]) -> None:
        nonlocal best_rank
        if rank is None:
            return
        if best_rank is None or rank < best_rank:
            best_rank = rank

    id_lower = entry["id_lower"]
    if id_lower:
        if query_lower == id_lower:
            consider(make_rank(0, 0, len(id_lower), 0))
        elif id_lower.startswith(query_lower):
            consider(make_rank(3, 0, len(id_lower), 0))
        else:
            pos = id_lower.find(query_lower)
            if pos != -1:
                consider(make_rank(6, pos, len(id_lower), 0))

    name_lower = entry["name_lower"]
    if name_lower:
        if query_lower == name_lower:
            consider(make_rank(1, 0, len(name_lower), 1))
        elif name_lower.startswith(query_lower):
            consider(make_rank(4, 0, len(name_lower), 1))
        else:
            pos = name_lower.find(query_lower)
            if pos != -1:
                consider(make_rank(7, pos, len(name_lower), 1))

    for token in entry["tokens"]:
        lower = token.get("lower", "")
        priority = token.get("priority", 5)
        if not lower:
            continue
        if query_lower == lower:
            consider(make_rank(2, 0, len(lower), priority))
            continue
        if lower.startswith(query_lower):
            consider(make_rank(5, 0, len(lower), priority))
            continue
        pos = lower.find(query_lower)
        if pos != -1:
            consider(make_rank(8, pos, len(lower), priority))

    if query_normalised and query_normalised != query_lower:
        id_norm = entry.get("id_normalised")
        if id_norm:
            if query_normalised == id_norm:
                consider(make_rank(9, 0, len(id_norm), 0))
            else:
                pos = id_norm.find(query_normalised)
                if pos != -1:
                    consider(make_rank(12, pos, len(id_norm), 0))

        name_norm = entry.get("name_normalised")
        if name_norm:
            if query_normalised == name_norm:
                consider(make_rank(10, 0, len(name_norm), 1))
            else:
                pos = name_norm.find(query_normalised)
                if pos != -1:
                    consider(make_rank(13, pos, len(name_norm), 1))

        for token in entry["tokens"]:
            norm = token.get("normalised")
            priority = token.get("priority", 5)
            if not norm:
                continue
            if query_normalised == norm:
                consider(make_rank(11, 0, len(norm), priority))
                continue
            pos = norm.find(query_normalised)
            if pos != -1:
                consider(make_rank(14, pos, len(norm), priority))

    return best_rank


@app.get("/api/search")
def search(
    q: Optional[str] = Query(None, min_length=1),
    query: Optional[str] = Query(None, min_length=1),
    limit: int = Query(10, ge=1, le=50),
):
    """Search compounds by ID, name, synonym, or alias."""
    search_term_raw = query or q
    search_term = search_term_raw.strip() if isinstance(search_term_raw, str) else None
    if not search_term:
        raise HTTPException(status_code=422, detail="Missing search parameter")

    _ensure_compound_indexes()

    query_lower = search_term.lower()
    query_normalised = _normalise_token(search_term)
    matched: List[Tuple[Tuple[int, int, int, int, str], Dict[str, Any]]] = []

    for entry in _COMPOUND_SEARCH_CACHE.values():
        rank = _score_search_entry(entry, query_lower, query_normalised)
        if rank is None:
            continue
        matched.append((rank, entry["compound"]))

    matched.sort(key=lambda item: item[0])
    results = [comp for _, comp in matched[:limit]]

    return {"results": results}

@app.get("/api/interaction")
def interaction(a: str, b: str):
    """Get interaction details between two compounds by id or name."""
    a_id = resolve_compound(a)
    b_id = resolve_compound(b)
    if not a_id or not b_id:
        raise HTTPException(status_code=404, detail="One or both compounds not found")

    _ensure_interaction_lookup()
    inter = _INTERACTION_LOOKUP.get((a_id, b_id)) or _INTERACTION_LOOKUP.get((b_id, a_id))
    if not inter:
        raise HTTPException(status_code=404, detail="No known interaction")

    risk_score = compute_risk(inter)
    sources_detail = [SOURCES[sid] for sid in inter.get("sources", []) if sid in SOURCES]
    return {"interaction": inter, "risk_score": risk_score, "sources": sources_detail}

class StackRequest(BaseModel):
    """Request payload for stack checks with input validation and alias support."""

    compounds: conlist(str, min_items=2)

    @root_validator(pre=True)
    def _alias_items(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if "compounds" not in values and "items" in values:
            values["compounds"] = values.pop("items")
        return values

    @validator("compounds", pre=True)
    def _validate_compounds(cls, value: Any) -> List[str]:
        if not isinstance(value, list):
            raise ValueError("compounds must be provided as a list of strings")
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if len(cleaned) < 2:
            raise ValueError("Provide at least two compounds to analyse a stack")
        return cleaned

def _classify_risk_bucket(interaction: Dict[str, Any], score: float) -> Tuple[str, str]:
    """Return a simple (bucket, action) tuple for stack responses."""

    severity = str(interaction.get("severity", "")).lower()
    action = str(interaction.get("action", "")).strip() or "Review"

    if severity == "severe" or score >= 2.5:
        return "High", action or "Avoid"
    if severity == "moderate" or score >= 1.5:
        return "Caution", action or "Monitor"
    return "Low", action or "No issue"


@app.post("/api/stack/check")
def check_stack(payload: StackRequest):
    """Check interactions within a stack of compounds."""

    input_items = payload.compounds
    resolved_ids: List[str] = []
    for ident in input_items:
        cid = resolve_compound(ident)
        if not cid:
            raise HTTPException(status_code=404, detail=f"Compound not found: {ident}")
        resolved_ids.append(cid)

    length = len(resolved_ids)
    matrix: List[List[Optional[float]]] = [[None for _ in range(length)] for _ in range(length)]
    interactions_out: List[Dict[str, Any]] = []

    _ensure_interaction_lookup()
    for i in range(length):
        for j in range(i + 1, length):
            a_id = resolved_ids[i]
            b_id = resolved_ids[j]
            inter = _INTERACTION_LOOKUP.get((a_id, b_id)) or _INTERACTION_LOOKUP.get((b_id, a_id))
            if not inter:
                continue

            score = compute_risk(inter)
            matrix[i][j] = score
            matrix[j][i] = score

            bucket, resolved_action = _classify_risk_bucket(inter, score)
            record = {
                "a": a_id,
                "b": b_id,
                "severity": inter.get("severity"),
                "evidence": inter.get("evidence"),
                "effect": inter.get("effect"),
                "action": inter.get("action"),
                "action_resolved": resolved_action,
                "bucket": bucket,
                "risk_score": score,
            }
            interactions_out.append(record)

    return {
        "items": input_items,
        "resolved_items": resolved_ids,
        "matrix": matrix,
        "cells": interactions_out,
        "interactions": interactions_out,
    }

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
