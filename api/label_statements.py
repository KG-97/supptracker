"""Read-only API for verbatim FDA supplement label statements."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

router = APIRouter()

# Anchored to the repository root so the corpus is found whatever directory the server starts in.
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "openfda_supplement_statements"
STATEMENT_FIELDS = [
    "statement_id",
    "record_kind",
    "review_status",
    "supplement_id",
    "supplement_name",
    "supplement_kind",
    "drug_id",
    "drug_names_raw",
    "sentence",
    "matched_text",
    "section",
    "set_id",
    "label_id",
    "effective_time",
    "label_count",
    "source_url",
    "retrieved_at",
    "rights_status",
]
PAIR_FIELDS = ["supplement_id", "drug_id", "statements", "labels"]
FIXED_VALUES = {
    "record_kind": "fda_label_statement",
    "review_status": "fda_approved_label_text_not_reviewed_by_supptracker",
    "section": "DRUG INTERACTIONS",
    "rights_status": "cc0_unless_otherwise_noted",
}
GROUP_KINDS = {"otc_class", "generic_class", "mineral_class"}
DISCLAIMER = (
    "FDA-approved label text, quoted verbatim, not reviewed or assessed by "
    "SuppTracker, not medical advice, absence of a statement does not mean a "
    "combination is safe."
)


def _empty_dataset(reason: str) -> Dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "statements": [],
        "pairs": [],
        "manifest": {},
    }


def _dataset_directory(data_dir: Optional[str | Path] = None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    return Path(
        os.getenv("SUPPTRACKER_LABEL_STATEMENTS_DIR", str(DEFAULT_DATA_DIR))
    )


def _read_csv(
    path: Path, required_fields: List[str]
) -> tuple[Optional[List[Dict[str, str]]], Optional[str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if fieldnames is None or any(
                field not in fieldnames for field in required_fields
            ):
                return None, "missing_required_column"
            return [
                {key: str(value or "") for key, value in row.items()}
                for row in reader
            ], None
    except (OSError, UnicodeError, csv.Error):
        return None, "unreadable_file"


def load_label_statements(
    data_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Load the complete statement corpus or disable it as one unit."""

    directory = _dataset_directory(data_dir)
    if not directory.is_dir():
        return _empty_dataset("missing_directory")

    files = {
        "statements": directory / "statements.csv",
        "pairs": directory / "pairs.csv",
        "manifest": directory / "manifest.json",
    }
    for name, path in files.items():
        if not path.is_file():
            return _empty_dataset(f"missing_required_file:{name}")

    statements, error = _read_csv(files["statements"], STATEMENT_FIELDS)
    if error:
        return _empty_dataset(f"{error}:statements")
    pairs, error = _read_csv(files["pairs"], PAIR_FIELDS)
    if error:
        return _empty_dataset(f"{error}:pairs")

    try:
        manifest = json.loads(files["manifest"].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _empty_dataset("unreadable_file:manifest")
    if not isinstance(manifest, dict):
        return _empty_dataset("invalid_manifest")

    assert statements is not None
    assert pairs is not None

    statement_ids = set()
    calculated_pairs: Dict[tuple[str, str], List[Dict[str, str]]] = {}
    for row in statements:
        statement_id = row.get("statement_id", "")
        if not statement_id:
            return _empty_dataset("invalid_statement_id")
        if statement_id in statement_ids:
            return _empty_dataset("duplicate_statement_id")
        statement_ids.add(statement_id)

        for field, expected in FIXED_VALUES.items():
            if row.get(field) != expected:
                return _empty_dataset(f"invalid_fixed_value:{field}")

        supplement_id = row.get("supplement_id", "")
        drug_id = row.get("drug_id", "")
        if not supplement_id or not drug_id or not row.get("sentence", ""):
            return _empty_dataset("invalid_statement_row")
        try:
            if int(row.get("label_count", "")) < 1:
                raise ValueError
        except ValueError:
            return _empty_dataset("invalid_statement_row")
        calculated_pairs.setdefault((supplement_id, drug_id), []).append(row)

    pair_keys = set()
    for row in pairs:
        supplement_id = row.get("supplement_id", "")
        drug_id = row.get("drug_id", "")
        key = (supplement_id, drug_id)
        if not supplement_id or not drug_id or key in pair_keys:
            return _empty_dataset("invalid_pairs")
        pair_keys.add(key)
        try:
            statement_count = int(row.get("statements", ""))
            label_count = int(row.get("labels", ""))
        except ValueError:
            return _empty_dataset("invalid_pairs")
        expected_rows = calculated_pairs.get(key, [])
        if statement_count != len(expected_rows):
            return _empty_dataset("invalid_pairs")
        if label_count != sum(
            int(statement["label_count"]) for statement in expected_rows
        ):
            return _empty_dataset("invalid_pairs")

    if pair_keys != set(calculated_pairs):
        return _empty_dataset("invalid_pairs")

    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        return _empty_dataset("invalid_manifest")
    expected_counts = {
        "statements": len(statements),
        "distinct_pairs": len(calculated_pairs),
        "distinct_supplements": len(
            {row["supplement_id"] for row in statements}
        ),
        "distinct_drugs": len({row["drug_id"] for row in statements}),
    }
    if any(counts.get(name) != value for name, value in expected_counts.items()):
        return _empty_dataset("manifest_counts_mismatch")

    return {
        "status": "available",
        "reason": None,
        "statements": statements,
        "pairs": pairs,
        "manifest": manifest,
    }


def _safe_load(data_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    """Never let a problem in this optional corpus stop the application from starting."""

    try:
        return load_label_statements(data_dir)
    except Exception:  # noqa: BLE001 - any unexpected fault disables the feature as a whole
        return _empty_dataset("load_error")


LABEL_STATEMENTS = _safe_load()


def reload_label_statements(
    data_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Reload the isolated corpus; used by tests and controlled deployments."""

    global LABEL_STATEMENTS
    LABEL_STATEMENTS = _safe_load(data_dir)
    return LABEL_STATEMENTS


def dataset_status() -> str:
    return str(LABEL_STATEMENTS["status"])


def loaded_count() -> int:
    return len(LABEL_STATEMENTS["statements"])


def _envelope() -> Dict[str, str]:
    return {
        "record_kind": FIXED_VALUES["record_kind"],
        "review_status": FIXED_VALUES["review_status"],
        "disclaimer": DISCLAIMER,
    }


def _unavailable_response() -> Dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": LABEL_STATEMENTS["reason"],
        "assessment": "not_assessed",
        **_envelope(),
    }


def _statement_item(row: Dict[str, str]) -> Dict[str, Any]:
    item = {field: row[field] for field in STATEMENT_FIELDS}
    item["is_group_term"] = row["supplement_kind"] in GROUP_KINDS
    item["label_url"] = (
        "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid="
        f"{row['set_id']}"
    )
    return item


def _supplement_summary() -> List[Dict[str, Any]]:
    pair_counts: Dict[str, int] = {}
    for pair in LABEL_STATEMENTS["pairs"]:
        supplement_id = pair["supplement_id"]
        pair_counts[supplement_id] = pair_counts.get(supplement_id, 0) + 1

    supplements: Dict[str, Dict[str, str]] = {}
    for row in LABEL_STATEMENTS["statements"]:
        supplements.setdefault(
            row["supplement_id"],
            {
                "supplement_name": row["supplement_name"],
                "supplement_kind": row["supplement_kind"],
            },
        )

    return [
        {
            "supplement_id": supplement_id,
            "supplement_name": details["supplement_name"],
            "supplement_kind": details["supplement_kind"],
            "is_group_term": details["supplement_kind"] in GROUP_KINDS,
            "pair_count": pair_counts.get(supplement_id, 0),
        }
        for supplement_id, details in sorted(supplements.items())
    ]


@router.get("/api/label-statements/summary")
def label_statements_summary() -> Dict[str, Any]:
    """Describe the isolated verbatim-label corpus."""

    if LABEL_STATEMENTS["status"] != "available":
        return {
            **_unavailable_response(),
            "counts": {
                "statements": 0,
                "pairs": 0,
                "supplements": 0,
                "drugs": 0,
            },
            "retrieved_at": None,
            "source": "",
            "license": "",
            "license_url": "",
            "supplements": [],
        }

    statements = LABEL_STATEMENTS["statements"]
    manifest = LABEL_STATEMENTS["manifest"]
    source = manifest.get("source", {})
    if not isinstance(source, dict):
        source = {}
    retrieved_values = sorted(
        {row["retrieved_at"] for row in statements if row["retrieved_at"]}
    )
    return {
        "status": "available",
        **_envelope(),
        "counts": {
            "statements": len(statements),
            "pairs": len(LABEL_STATEMENTS["pairs"]),
            "supplements": len({row["supplement_id"] for row in statements}),
            "drugs": len({row["drug_id"] for row in statements}),
        },
        "retrieved_at": {
            "earliest": retrieved_values[0] if retrieved_values else None,
            "latest": retrieved_values[-1] if retrieved_values else None,
        },
        "source": source.get("api_url", ""),
        "license": source.get("license", ""),
        "license_url": source.get("license_url", ""),
        "supplements": _supplement_summary(),
    }


@router.get("/api/label-statements")
def list_label_statements(
    supplement: Optional[str] = None,
    drug: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Return verbatim FDA-label statements without clinical interpretation."""

    if LABEL_STATEMENTS["status"] != "available":
        return {
            **_unavailable_response(),
            "total": 0,
            "items": [],
        }

    records = LABEL_STATEMENTS["statements"]
    if supplement is not None:
        records = [
            row for row in records if row["supplement_id"] == supplement
        ]
    if drug:
        needle = drug.casefold()
        records = [
            row
            for row in records
            if needle in row["drug_id"].casefold()
            or needle in row["drug_names_raw"].casefold()
        ]
    if q:
        needle = q.casefold()
        records = [
            row for row in records if needle in row["sentence"].casefold()
        ]

    response: Dict[str, Any] = {
        "status": "available",
        **_envelope(),
        "total": len(records),
        "items": [_statement_item(row) for row in records[offset : offset + limit]],
    }
    if not records and any(
        value is not None and value != "" for value in (supplement, drug, q)
    ):
        response["assessment"] = "not_assessed"
    return response


@router.get("/api/label-statements/pair")
def label_statements_pair(supplement: str, drug: str) -> Dict[str, Any]:
    """Return verbatim statements for one exact supplement and drug identifier."""

    if LABEL_STATEMENTS["status"] != "available":
        return {
            **_unavailable_response(),
            "total": 0,
            "items": [],
        }

    records = [
        row
        for row in LABEL_STATEMENTS["statements"]
        if row["supplement_id"] == supplement and row["drug_id"] == drug
    ]
    response: Dict[str, Any] = {
        "status": "available",
        **_envelope(),
        "supplement_id": supplement,
        "drug_id": drug,
        "total": len(records),
        "items": [_statement_item(row) for row in records],
    }
    if not records:
        response["assessment"] = "not_assessed"
    return response
