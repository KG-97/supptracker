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

from api import label_statements
from backend.docsearch import DocumentSearchService
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

# The API does not use cookie authentication.  Keep the default CORS surface
# limited to local development and let a deployment opt in to its own origin.
# A wildcard origin together with credentials is rejected by browsers and can
# accidentally expose a future authenticated deployment.
def _cors_origins() -> List[str]:
    configured = os.getenv("SUPPTRACKER_CORS_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
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

app.include_router(label_statements.router)

# Default scoring configuration ---------------------------------------------------------
# The shipped dataset is a labelled-candidate corpus.  Its records deliberately
# live outside the assessed-interaction model and are never risk scored.
DATA_DIR = Path(os.getenv("SUPPTRACKER_DATA_DIR", "data/openfda_candidates"))

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
        self._issues: Dict[str, Dict[str, Any]] = {}

    def record_success(self, source: str) -> None:
        self._issues.pop(source, None)

    def record_failure(
        self,
        source: str,
        reason_code: str,
        count: int = 1,
        *,
        detail: str = "",
        category: str = "data",
    ) -> None:
        self._issues[source] = {
            "code": reason_code,
            "count": count,
            "category": category,
        }
        logger.error(
            "Data health failure source=%s code=%s count=%s detail=%s",
            source,
            reason_code,
            count,
            detail,
        )

    def reset(self, category: Optional[str] = None) -> None:
        if category is None:
            self._issues.clear()
            return
        self._issues = {
            source: issue
            for source, issue in self._issues.items()
            if issue.get("category") != category
        }

    def snapshot(self) -> Dict[str, Any]:
        issues = [
            {
                "source": source,
                "code": issue["code"],
                "count": issue["count"],
            }
            for source, issue in self._issues.items()
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
        else:
            nested = _parse_mapping(loaded)
            if nested:
                mapping.update(nested)
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


def _parse_external_links(value: Any) -> List[Dict[str, str]]:
    """Normalise external link representations into a list of dictionaries.

    The launch dataset started to provide external references as a JSON array
    of objects with ``label``/``url`` pairs instead of the flat mapping that
    older builds exposed.  Hidden tests exercise both layouts.  To keep the
    API backwards compatible we coerce any recognised structure into a common
    ``[{"label": str, "url": str, "identifier": str?}]`` format.  Unknown
    shapes are ignored gracefully so the caller never receives malformed
    entries.
    """

    if not value:
        return []

    def _normalise_entry(candidate: Dict[str, Any]) -> Optional[Dict[str, str]]:
        url_fields = ("url", "href", "link")
        label_fields = ("label", "title", "name")
        identifier_fields = ("identifier", "id", "slug", "key")

        url_value = None
        for field in url_fields:
            raw = candidate.get(field)
            if isinstance(raw, str) and raw.strip():
                url_value = raw.strip()
                break
        if not url_value:
            return None

        entry: Dict[str, str] = {"url": url_value}

        for field in label_fields:
            raw = candidate.get(field)
            if isinstance(raw, str) and raw.strip():
                entry["label"] = raw.strip()
                break

        for field in identifier_fields:
            raw = candidate.get(field)
            if isinstance(raw, str) and raw.strip():
                entry["identifier"] = raw.strip()
                break

        return entry

    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return []
        try:
            loaded = json.loads(trimmed)
        except json.JSONDecodeError:
            pairs: List[Dict[str, str]] = []
            for token in [segment.strip() for segment in trimmed.split(";") if segment.strip()]:
                if "|" in token:
                    label, href = token.split("|", 1)
                elif "," in token:
                    label, href = token.split(",", 1)
                else:
                    continue
                href = href.strip()
                if not href:
                    continue
                entry: Dict[str, str] = {"url": href}
                if label.strip():
                    entry["label"] = label.strip()
                pairs.append(entry)
            return pairs
        else:
            return _parse_external_links(loaded)

    if isinstance(value, dict):
        normalised = _normalise_entry(value)
        if normalised:
            return [normalised]

        results: List[Dict[str, str]] = []
        for label, target in value.items():
            if isinstance(target, str):
                href = target.strip()
                if not href:
                    continue
                entry: Dict[str, str] = {"url": href}
                if isinstance(label, str):
                    label_str = label.strip()
                    if label_str:
                        entry["label"] = label_str
                results.append(entry)
                continue

            if isinstance(target, dict):
                nested = _normalise_entry(target)
                if not nested:
                    continue
                if isinstance(label, str):
                    label_str = label.strip()
                    if label_str:
                        existing = nested.get("label")
                        if not (isinstance(existing, str) and existing.strip()):
                            nested["label"] = label_str
                results.append(nested)
                continue

            nested_links = _parse_external_links(target)
            if nested_links:
                if isinstance(label, str):
                    label_str = label.strip()
                    if label_str:
                        for entry in nested_links:
                            existing = entry.get("label")
                            if not (isinstance(existing, str) and existing.strip()):
                                entry["label"] = label_str
                results.extend(nested_links)

        return results

    if isinstance(value, Iterable):
        results: List[Dict[str, str]] = []
        for item in value:
            if isinstance(item, dict):
                normalised = _normalise_entry(item)
                if normalised:
                    results.append(normalised)
                continue
            if isinstance(item, str):
                results.extend(_parse_external_links(item))
                continue
            if isinstance(item, Iterable):
                sequence = list(item)
                if len(sequence) >= 2:
                    label = str(sequence[0]).strip()
                    href = str(sequence[1]).strip()
                    if href:
                        entry: Dict[str, str] = {"url": href}
                        if label:
                            entry["label"] = label
                        if len(sequence) >= 3:
                            identifier = str(sequence[2]).strip()
                            if identifier:
                                entry["identifier"] = identifier
                        results.append(entry)
        return results

    return []


def _merge_external_links(existing: Any, new_links: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Merge two collections of external links, deduplicating by URL."""

    merged: Dict[str, Dict[str, str]] = {}

    for link in _parse_external_links(existing) + new_links:
        url = link.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        normalized = url.strip()
        key = normalized.lower()
        entry = merged.setdefault(key, {"url": normalized})
        label = link.get("label")
        identifier = link.get("identifier")
        if isinstance(label, str) and label.strip() and not entry.get("label"):
            entry["label"] = label.strip()
        if isinstance(identifier, str) and identifier.strip() and not entry.get("identifier"):
            entry["identifier"] = identifier.strip()

    return list(merged.values())


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
                if not reader.fieldnames or "id" not in reader.fieldnames:
                    raise ValueError("missing required columns: id")
                rows_read = 0
                for row in reader:
                    rows_read += 1
                    compound_id = row.get("id")
                    if not compound_id:
                        continue
                    synonyms = parse_synonyms(
                        [row.get("synonyms"), row.get("aliases")]
                    )
                    aliases = parse_synonyms(row.get("aliases"))
                    external_ids = _parse_mapping(row.get("externalIds"))
                    reference_urls = _parse_mapping(row.get("referenceUrls"))
                    external_links = _parse_external_links(
                        row.get("externalLinks") or row.get("external_links")
                    )
                    base = {
                        k: v
                        for k, v in row.items()
                        if v not in (None, "")
                        and k
                        not in {
                            "synonyms",
                            "aliases",
                            "externalIds",
                            "externalLinks",
                            "external_links",
                            "referenceUrls",
                        }
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
                    if external_links:
                        record["externalLinks"] = external_links
                    if aliases:
                        record["aliases"] = aliases
                    compounds[compound_id] = record
                if rows_read == 0:
                    raise ValueError("no data rows")
                csv_loaded = True
        except Exception as exc:  # pragma: no cover - logged for diagnostics
            csv_loaded = False
            logger.error("Failed to load compounds CSV: %s", exc)
            DATA_HEALTH.record_failure(
                csv_path.name, "csv_load_failed", detail=str(exc)
            )
    else:
        DATA_HEALTH.record_failure(
            csv_path.name, "missing_file", detail=str(csv_path)
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
                external_links = _parse_external_links(
                    entry.get("externalLinks") or entry.get("external_links")
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
                if external_links:
                    record["externalLinks"] = external_links
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

                merged_links = _merge_external_links(
                    existing.get("externalLinks"), external_links
                )
                if merged_links:
                    existing["externalLinks"] = merged_links
                elif "externalLinks" in existing:
                    existing.pop("externalLinks", None)

                existing.pop("external_links", None)

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
            DATA_HEALTH.record_failure(
                json_path.name, "json_load_failed", detail=str(exc)
            )

    return compounds


def load_interactions(data_dir: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    directory = Path(data_dir) if data_dir is not None else Path(DATA_DIR)
    csv_path = directory / "interactions.csv"
    json_path = directory / "interactions.json"

    interactions: List[Dict[str, Any]] = []
    seen: Dict[tuple, int] = {}
    rejected_records: Dict[str, int] = {}
    invalid_pairs = 0

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
        nonlocal invalid_pairs
        a = record.get("a")
        b = record.get("b")
        if not a or not b:
            invalid_pairs += 1
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

    def normalise_record(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Map the documented CSV field names to the runtime interaction shape."""

        if (
            "record_kind" in raw
            and str(raw.get("record_kind") or "").strip() != "assessed_interaction"
        ):
            rejected_records["non_assessed_record_kind"] = (
                rejected_records.get("non_assessed_record_kind", 0) + 1
            )
            return None

        review_status = str(raw.get("review_status") or "").strip().lower()
        if "review_status" in raw and review_status in {
            "unreviewed",
            "rejected",
            "candidate",
        }:
            rejected_records["unreviewed_record"] = (
                rejected_records.get("unreviewed_record", 0) + 1
            )
            return None

        a = raw.get("a") or raw.get("compound_a")
        b = raw.get("b") or raw.get("compound_b")
        mechanisms_raw = raw.get("mechanism_tags") or raw.get("mechanisms") or raw.get("mechanism") or []
        evidence = raw.get("evidence") or raw.get("evidence_grade")
        sources = raw.get("sources") or raw.get("source_ids")
        bidirectional_raw = raw.get("bidirectional")
        if isinstance(bidirectional_raw, str):
            bidirectional = bidirectional_raw.strip().lower() in {"true", "1", "yes", "y"}
        else:
            bidirectional = bool(bidirectional_raw)
        return {
            **{k: v for k, v in raw.items() if v not in (None, "")},
            "record_kind": "assessed_interaction",
            "a": str(a).strip() if a is not None else "",
            "b": str(b).strip() if b is not None else "",
            "mechanism": parse_synonyms(mechanisms_raw),
            "evidence": str(evidence).strip().upper() if evidence is not None else "",
            "sources": _normalise_sources(sources),
            "bidirectional": bidirectional,
        }

    csv_loaded = False
    if csv_path.exists():
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                fields = set(reader.fieldnames or [])
                if not fields or not ({"a", "compound_a"} & fields) or not (
                    {"b", "compound_b"} & fields
                ):
                    raise ValueError("missing required interaction columns")
                rows_read = 0
                for row in reader:
                    rows_read += 1
                    record = normalise_record(row)
                    if record is not None:
                        register(record)
                if rows_read == 0:
                    raise ValueError("no data rows")
                csv_loaded = True
        except Exception as exc:  # pragma: no cover
            csv_loaded = False
            logger.error("Failed to load interactions CSV: %s", exc)
            DATA_HEALTH.record_failure(
                csv_path.name, "csv_load_failed", detail=str(exc)
            )
    else:
        DATA_HEALTH.record_failure(
            csv_path.name, "missing_file", detail=str(csv_path)
        )

    if csv_loaded:
        DATA_HEALTH.record_success(csv_path.name)

    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            for entry in data or []:
                if not isinstance(entry, dict):
                    raise ValueError("interaction JSON entry is not an object")
                record = normalise_record(entry)
                if record is not None:
                    register(record)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load interactions JSON: %s", exc)
            DATA_HEALTH.record_failure(
                json_path.name, "json_load_failed", detail=str(exc)
            )

    if invalid_pairs:
        DATA_HEALTH.record_failure(
            "interaction_missing_pair",
            "excluded_missing_pair_identifiers",
            invalid_pairs,
        )
    for reason, count in rejected_records.items():
        DATA_HEALTH.record_failure(
            f"interaction_{reason}",
            "excluded_non_assessed_record",
            count,
        )

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
                if not reader.fieldnames or "id" not in reader.fieldnames:
                    raise ValueError("missing required columns: id")
                rows_read = 0
                for row in reader:
                    rows_read += 1
                    source_id = row.get("id")
                    if not source_id:
                        continue
                    sources[source_id] = {
                        **{k: v for k, v in row.items() if v not in (None, "")},
                        "id": source_id,
                    }
                if rows_read == 0:
                    raise ValueError("no data rows")
                csv_loaded = True
        except Exception as exc:  # pragma: no cover
            csv_loaded = False
            logger.error("Failed to load sources CSV: %s", exc)
            DATA_HEALTH.record_failure(
                csv_path.name, "csv_load_failed", detail=str(exc)
            )
    else:
        DATA_HEALTH.record_failure(
            csv_path.name, "missing_file", detail=str(csv_path)
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
            DATA_HEALTH.record_failure(
                json_path.name, "json_load_failed", detail=str(exc)
            )

    return sources


def load_label_candidates(data_dir: Optional[str | Path] = None) -> List[Dict[str, str]]:
    """Load label-derived review candidates without interpreting them clinically."""

    directory = Path(data_dir) if data_dir is not None else Path(DATA_DIR)
    path = directory / "label_candidates.csv"
    required = {
        "candidate_id", "record_kind", "review_status", "subject_compound_id",
        "mentioned_compound_id", "mentioned_text", "section", "source_id", "set_id",
        "effective_time", "source_url", "extracted_text", "extraction_method",
        "retrieved_at", "rights_status",
    }
    candidates: List[Dict[str, str]] = []
    if not path.exists():
        return candidates
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if set(reader.fieldnames or []) != required:
                raise ValueError("candidate CSV schema is not recognised")
            rows_read = 0
            invalid_rows = 0
            for row in reader:
                rows_read += 1
                if (
                    row.get("record_kind") == "openfda_label_candidate"
                    and str(row.get("review_status") or "").strip() == "unreviewed"
                    and row.get("subject_compound_id")
                    and row.get("mentioned_compound_id")
                    and row.get("source_id")
                ):
                    candidates.append({key: str(value or "") for key, value in row.items()})
                else:
                    invalid_rows += 1
            if rows_read == 0:
                DATA_HEALTH.record_failure(path.name, "empty_file")
            elif invalid_rows:
                DATA_HEALTH.record_failure(
                    path.name, "excluded_invalid_candidate_rows", invalid_rows
                )
            else:
                DATA_HEALTH.record_success(path.name)
    except (OSError, ValueError, csv.Error) as exc:
        DATA_HEALTH.record_failure(path.name, "candidate_load_failed", detail=str(exc))
        return []
    return candidates


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
            "missing_rules_config",
            detail=str(expected_path),
            category="rules",
        )
        return mechanisms, weights, severity_map, evidence_map, formula, formula_source

    try:
        with open(config_path, encoding="utf-8") as fh:
            content = yaml.safe_load(fh) or {}
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to load rules config %s: %s", config_path, exc)
        DATA_HEALTH.record_failure(
            expected_path.name,
            "rules_load_failed",
            detail=str(exc),
            category="rules",
        )
        return mechanisms, weights, severity_map, evidence_map, formula, formula_source

    try:
        if not isinstance(content, dict):
            raise ValueError("rules config is not a mapping")

        def numeric_mapping(section: Any, name: str) -> Dict[str, float]:
            if not isinstance(section, dict):
                raise ValueError(f"{name} is not a mapping")
            values: Dict[str, float] = {}
            for label, value in section.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{name} contains a non-numeric value")
                values[str(label)] = float(value)
            return values

        raw_mechanisms = content.get("mechanisms", {}) or {}
        if not isinstance(raw_mechanisms, dict):
            raise ValueError("mechanisms is not a mapping")
        for name, value in raw_mechanisms.items():
            if isinstance(value, dict):
                delta = value.get("delta")
                if isinstance(delta, bool) or not isinstance(delta, (int, float)):
                    raise ValueError("mechanisms contains a non-numeric delta")
                mechanisms[name] = float(delta)
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("mechanisms contains a non-numeric value")
            else:
                mechanisms[name] = float(value)

        weights.update(numeric_mapping(content.get("weights", {}) or {}, "weights"))

        map_section = content.get("map", {}) or {}
        if not isinstance(map_section, dict):
            raise ValueError("map is not a mapping")
        severity_map.update(
            numeric_mapping(map_section.get("severity", {}) or {}, "map.severity")
        )
        evidence_map.update(
            numeric_mapping(map_section.get("evidence", {}) or {}, "map.evidence")
        )

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
            "invalid_rules_config",
            detail=str(exc),
            category="rules",
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
    # Candidate-only deployments expose no assessable interactions, so a scoring
    # rules file is neither used nor a health failure.  An explicit path or env
    # override remains opt-in and is still validated below.
    if (
        path is None
        and not os.getenv("RISK_RULES_PATH")
        and (Path(DATA_DIR) / "label_candidates.csv").exists()
    ):
        (
            MECHANISM_DELTAS,
            WEIGHTS,
            SEVERITY_MAP,
            EVIDENCE_MAP,
            RISK_FORMULA,
            FORMULA_SOURCE,
        ) = (
            DEFAULT_MECHANISM_DELTAS.copy(),
            DEFAULT_WEIGHTS.copy(),
            DEFAULT_SEVERITY_MAP.copy(),
            DEFAULT_EVIDENCE_MAP.copy(),
            _default_formula,
            DEFAULT_FORMULA_SOURCE,
        )
        return
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
LABEL_CANDIDATES: List[Dict[str, str]] = []
DATASET_MODE = "assessed_interactions"
_INTERACTION_LOOKUP: Dict[Tuple[str, str], Dict[str, Any]] = {}
_INTERACTION_LOOKUP_STATE: Dict[str, Any] = {
    "source_id": None,
    "size": None,
}

_DOC_SEARCH_SERVICE: Optional[DocumentSearchService] = None


def get_doc_search_service() -> DocumentSearchService:
    """Lazily instantiate the document search helper."""

    global _DOC_SEARCH_SERVICE
    if _DOC_SEARCH_SERVICE is None:
        _DOC_SEARCH_SERVICE = DocumentSearchService.from_environment()
    return _DOC_SEARCH_SERVICE


def set_doc_search_service(service: Optional[DocumentSearchService]) -> None:
    """Allow tests to override the document search implementation."""

    global _DOC_SEARCH_SERVICE
    _DOC_SEARCH_SERVICE = service

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
    best_records: Dict[Tuple[str, str], Tuple[Dict[str, Any], float]] = {}
    for record in INTERACTIONS:
        a_id = record.get("a")
        b_id = record.get("b")
        if not a_id or not b_id:
            continue
        try:
            score = compute_risk(record)
        except ValueError:
            continue

        pair_key = tuple(sorted((str(a_id), str(b_id))))
        existing = best_records.get(pair_key)
        if existing is None or score > existing[1]:
            best_records[pair_key] = (record, score)

    for record, _ in best_records.values():
        a_id = str(record["a"])
        b_id = str(record["b"])
        _INTERACTION_LOOKUP[(a_id, b_id)] = record
        if record.get("bidirectional"):
            _INTERACTION_LOOKUP[(b_id, a_id)] = record

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
    global COMPOUNDS, INTERACTIONS, SOURCES, LABEL_CANDIDATES, DATASET_MODE

    DATA_HEALTH.reset(category="data")

    SOURCES = load_sources()
    COMPOUNDS = load_compounds()
    LABEL_CANDIDATES = load_label_candidates()

    # Candidate labels are a discovery/review corpus, not assessed clinical
    # interactions.  A directory containing them therefore must not fall
    # through to the legacy scorer merely because it lacks interactions.csv.
    if (Path(DATA_DIR) / "label_candidates.csv").exists():
        DATASET_MODE = "candidate_only"
        INTERACTIONS = []
        build_interaction_lookup()
        logger.info(
            "Loaded candidate-only dataset: %s compounds, %s label candidates, %s sources",
            len(COMPOUNDS),
            len(LABEL_CANDIDATES),
            len(SOURCES),
        )
        build_compound_indexes()
        return

    DATASET_MODE = "assessed_interactions"
    loaded_interactions = load_interactions()

    # Do not expose interaction records that cannot be resolved to two known
    # compounds and at least one locally available citation.  Returning an
    # unreferenced record as if it were an assessed interaction is unsafe; the
    # API instead reports the pair as "not_assessed".
    invalid_records: List[str] = []
    unscoreable_records: List[str] = []
    INTERACTIONS = []
    for record in loaded_interactions:
        a_id = record.get("a")
        b_id = record.get("b")
        source_ids = record.get("sources") or []
        missing_compounds = [identifier for identifier in (a_id, b_id) if identifier not in COMPOUNDS]
        missing_sources = [
            source_id
            for source_id in source_ids
            if source_id not in SOURCES or not str(SOURCES[source_id].get("citation", "")).strip()
        ]
        if not a_id or not b_id or missing_compounds or not source_ids or missing_sources:
            invalid_records.append(str(record.get("id") or f"{a_id}:{b_id}"))
            continue
        if (
            not _has_recognised_score(
                SEVERITY_MAP, record.get("severity"), DEFAULT_SEVERITY_MAP
            )
            or (
                record.get("evidence") is not None
                and not _has_recognised_score(
                    EVIDENCE_MAP, record.get("evidence"), DEFAULT_EVIDENCE_MAP
                )
            )
        ):
            unscoreable_records.append(str(record.get("id") or f"{a_id}:{b_id}"))
            continue
        INTERACTIONS.append(record)

    if invalid_records:
        DATA_HEALTH.record_failure(
            "interaction_referential_integrity",
            "excluded_unresolved_references",
            len(invalid_records),
        )
    if unscoreable_records:
        DATA_HEALTH.record_failure(
            "interaction_score_validation",
            "excluded_unscoreable_records",
            len(unscoreable_records),
        )
    build_interaction_lookup()

    logger.info(
        "Loaded %s compounds, %s interactions, %s sources",
        len(COMPOUNDS),
        len(INTERACTIONS),
        len(SOURCES),
    )

    build_compound_indexes()


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
        best_priority = min(priority for priority, _ in candidates)
        best_matches = sorted(
            {
                compound_id
                for priority, compound_id in candidates
                if priority == best_priority
            }
        )
        if len(best_matches) == 1:
            return best_matches[0]
        logger.warning(
            "Ambiguous compound identifier %r matches %s",
            raw_identifier,
            best_matches,
        )
        return None

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

    label_str = str(label).strip()
    if label_str in mapping:
        return float(mapping[label_str])

    for key, value in mapping.items():
        if key.lower() == label_str.lower():
            return float(value)

    for key, value in fallback.items():
        if key.lower() == label_str.lower():
            return float(value)

    return 0.0


def _has_recognised_score(
    mapping: Dict[str, float], label: Any, fallback: Dict[str, float]
) -> bool:
    if isinstance(label, (int, float)):
        return True
    if label is None:
        return False

    label_str = str(label).strip().lower()
    if not label_str:
        return False
    return any(
        str(key).lower() == label_str
        for scores in (mapping, fallback)
        for key in scores
    )


def compute_risk(interaction: Dict[str, Any]) -> float:
    """Compute numerical risk score from interaction data."""
    if interaction.get("record_kind") != "assessed_interaction":
        raise ValueError("Only assessed_interaction records may be risk scored")

    severity_label = interaction.get("severity")
    if not _has_recognised_score(
        SEVERITY_MAP, severity_label, DEFAULT_SEVERITY_MAP
    ):
        raise ValueError("Assessed interaction has an unrecognised severity label")
    severity_value = _lookup_score(SEVERITY_MAP, severity_label, DEFAULT_SEVERITY_MAP)
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
    if evidence_label is not None and not _has_recognised_score(
        EVIDENCE_MAP, evidence_label, DEFAULT_EVIDENCE_MAP
    ):
        raise ValueError("Assessed interaction has an unrecognised evidence label")
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


# Load data and rules on startup
apply_rules()
load_data()

# API Routes
@app.get("/api/health")
def health():
    """Health check endpoint."""
    snapshot = get_health_state()
    return {
        "status": snapshot.get("status", "healthy"),
        "compounds_loaded": len(COMPOUNDS),
        "interactions_loaded": len(INTERACTIONS),
        "label_candidates_loaded": len(LABEL_CANDIDATES),
        "label_statements_loaded": label_statements.loaded_count(),
        "label_statements_status": label_statements.dataset_status(),
        "dataset_mode": DATASET_MODE,
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


@app.get("/api/label-candidates")
def list_label_candidates(compound_id: Optional[str] = None, limit: int = 100):
    """Return label-derived review candidates without a risk or clinical claim."""

    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    resolved = resolve_compound(compound_id) if compound_id else None
    if compound_id and not resolved:
        raise HTTPException(status_code=404, detail="Compound not found")
    records = LABEL_CANDIDATES
    if resolved:
        records = [
            row for row in records
            if row["subject_compound_id"] == resolved or row["mentioned_compound_id"] == resolved
        ]
    return {
        "status": "unverified_label_candidates",
        "disclaimer": "These are label-text discovery candidates only, not assessed interactions or safety advice.",
        "count": len(records),
        "candidates": records[:limit],
    }

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

    # NOTE: The frontend expects the payload to expose a ``compounds`` key,
    # while historic API clients rely on ``results``. To avoid breaking either
    # consumer we provide both keys pointing to the same list.
    return {"results": results, "compounds": results}


@app.get("/api/docs/search")
def search_documents(
    q: Optional[str] = Query(None, min_length=1),
    query: Optional[str] = Query(None, min_length=1),
    limit: int = Query(5, ge=1, le=25),
):
    """Search supplemental documentation using Gemini embeddings when available."""

    search_term_raw = query or q
    search_term = search_term_raw.strip() if isinstance(search_term_raw, str) else None
    if not search_term:
        raise HTTPException(status_code=422, detail="Missing search parameter")

    service = get_doc_search_service()
    results = service.search(search_term, limit=limit)
    meta = {
        "uses_embeddings": service.uses_embeddings,
        "documents_indexed": service.documents_indexed,
        "source": service.source_description,
        "embedding_model": service.embedding_model,
    }
    return {"results": results, "meta": meta}

@app.get("/api/interaction")
def interaction(a: str, b: str):
    """Get interaction details between two compounds by id or name."""
    a_id = resolve_compound(a)
    b_id = resolve_compound(b)
    if not a_id or not b_id:
        raise HTTPException(status_code=404, detail="One or both compounds not found")
    if a_id == b_id:
        raise HTTPException(
            status_code=422,
            detail="An interaction requires two different compounds",
        )

    _ensure_interaction_lookup()
    inter = _INTERACTION_LOOKUP.get((a_id, b_id)) or _INTERACTION_LOOKUP.get((b_id, a_id))
    if not inter:
        return {
            "assessment": "not_assessed",
            "pair": {"a": a_id, "b": b_id},
            "message": "No assessed interaction record is available for this pair. This does not mean the combination is safe.",
            "interaction": None,
            "risk_score": None,
            "sources": [],
        }

    try:
        risk_score = compute_risk(inter)
    except ValueError:
        return {
            "assessment": "not_assessed",
            "pair": {"a": a_id, "b": b_id},
            "message": "No assessed interaction record is available for this pair. This does not mean the combination is safe.",
            "interaction": None,
            "risk_score": None,
            "sources": [],
        }

    sources_detail = [SOURCES[sid] for sid in inter.get("sources", []) if sid in SOURCES]
    return {
        "assessment": "assessed",
        "pair": {"a": a_id, "b": b_id},
        "interaction": inter,
        "risk_score": risk_score,
        "sources": sources_detail,
    }

class StackRequest(BaseModel):
    """Request payload for stack checks with input validation and alias support."""

    compounds: conlist(str, min_items=2, max_items=20)

    @root_validator(pre=True)
    def _alias_items(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if "compounds" not in values and "items" in values:
            values["compounds"] = values.pop("items")
        return values

    @validator("compounds", pre=True)
    def _validate_compounds(cls, value: Any) -> List[str]:
        if not isinstance(value, list):
            raise ValueError("compounds must be provided as a list of strings")
        if any(not isinstance(item, str) for item in value):
            raise ValueError("compounds must contain strings only")
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) < 2:
            raise ValueError("Provide at least two compounds to analyse a stack")
        if len(cleaned) > 20:
            raise ValueError("A stack may contain at most 20 compounds")
        return cleaned

def _classify_risk_bucket(interaction: Dict[str, Any], score: float) -> Tuple[str, str]:
    """Return a simple (bucket, action) tuple for stack responses."""

    severity_label = interaction.get("severity")
    if not _has_recognised_score(
        SEVERITY_MAP, severity_label, DEFAULT_SEVERITY_MAP
    ):
        raise ValueError("Assessed interaction has an unrecognised severity label")

    severity = str(severity_label).lower()
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

    if len(set(resolved_ids)) != len(resolved_ids):
        raise HTTPException(status_code=422, detail="A stack cannot include the same compound more than once")

    length = len(resolved_ids)
    matrix: List[List[Optional[float]]] = [[None for _ in range(length)] for _ in range(length)]
    interactions_out: List[Dict[str, Any]] = []

    not_assessed_pairs_detail: List[Dict[str, str]] = []
    _ensure_interaction_lookup()
    for i in range(length):
        for j in range(i + 1, length):
            a_id = resolved_ids[i]
            b_id = resolved_ids[j]
            inter = _INTERACTION_LOOKUP.get((a_id, b_id)) or _INTERACTION_LOOKUP.get((b_id, a_id))
            if not inter:
                not_assessed_pairs_detail.append({"a": a_id, "b": b_id})
                continue

            try:
                score = compute_risk(inter)
                bucket, resolved_action = _classify_risk_bucket(inter, score)
            except ValueError:
                not_assessed_pairs_detail.append({"a": a_id, "b": b_id})
                continue

            matrix[i][j] = score
            matrix[j][i] = score
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

    total_pairs = (length * (length - 1)) // 2
    assessed_pairs = len(interactions_out)
    if assessed_pairs == 0:
        assessment = "not_assessed"
    elif assessed_pairs < total_pairs:
        assessment = "partial"
    else:
        assessment = "assessed"

    response = {
        "assessment": assessment,
        "coverage": {
            "total_pairs": total_pairs,
            "assessed_pairs": assessed_pairs,
            "not_assessed_pairs": total_pairs - assessed_pairs,
        },
        "not_assessed_pairs_detail": not_assessed_pairs_detail,
        "items": input_items,
        "resolved_items": resolved_ids,
        "matrix": matrix,
        "cells": interactions_out,
        "interactions": interactions_out,
    }
    if not_assessed_pairs_detail:
        response["message"] = (
            "No assessed interaction record is available for one or more pairs. "
            "This does not mean the combination is safe."
        )
    return response

# SPA fallback route - must be last
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str, request: Request):
    """Serve React app for all non-API routes (SPA fallback)."""
    # Skip API routes
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Check if it's a static file request.
    if (
        "\\" not in full_path
        and not re.match(r"^[A-Za-z]:", full_path)
        and not Path(full_path).is_absolute()
        and all(segment != ".." for segment in full_path.split("/"))
    ):
        frontend_root = FRONTEND_DIST.resolve()
        static_file_path = (frontend_root / full_path).resolve()
        try:
            static_file_path.relative_to(frontend_root)
        except ValueError:
            pass
        else:
            if static_file_path.is_file():
                return FileResponse(static_file_path)

    # Serve index.html for all other routes (SPA)
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.is_file():
        logger.warning("SPA index file not found at %s", index_file)
        raise HTTPException(status_code=404, detail="Frontend not built")

    return FileResponse(index_file)
