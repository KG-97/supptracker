#!/usr/bin/env python3
"""Validate a SuppTracker openFDA supplement-statement dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


STATEMENT_FIELDS = [
    "statement_id", "record_kind", "review_status", "supplement_id",
    "supplement_name", "supplement_kind", "drug_id", "drug_names_raw",
    "sentence", "matched_text", "section", "set_id", "label_id",
    "effective_time", "label_count", "source_url", "retrieved_at",
    "rights_status",
]
PAIR_FIELDS = ["supplement_id", "drug_id", "statements", "labels"]
FIXED = {
    "record_kind": "fda_label_statement",
    "review_status": "fda_approved_label_text_not_reviewed_by_supptracker",
    "section": "DRUG INTERACTIONS",
    "rights_status": "cc0_unless_otherwise_noted",
}
FORBIDDEN = ("severity", "risk", "score", "safe", "grade")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def fail(failures: list[str], name: str, detail: str = "") -> None:
    failures.append(name if not detail else f"{name}: {detail}")


def read_csv(path: Path, expected: list[str], failures: list[str], name: str) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            actual = reader.fieldnames
            if actual != expected:
                fail(failures, f"{name}_header", f"expected {expected!r}, found {actual!r}")
                return []
            return list(reader)
    except (OSError, csv.Error) as exc:
        fail(failures, f"{name}_read", str(exc))
        return []


def load_terms(path: Path) -> dict[str, dict[str, Any]]:
    source = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, dict[str, Any]] = {}
    for raw in source["entries"]:
        entry_id = raw["id"]
        entries[entry_id] = {
            "match": re.compile(raw["match"], re.IGNORECASE),
            "exclude": [re.compile(item, re.IGNORECASE) for item in raw.get("exclude", [])],
        }
    return entries


def contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower() for token in FORBIDDEN) or contains_forbidden(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_forbidden(item) for item in value)
    return any(token in str(value).lower() for token in FORBIDDEN)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=Path("data/openfda_supplement_statements"), type=Path)
    parser.add_argument("--terms", required=True, type=Path)
    args = parser.parse_args()

    failures: list[str] = []
    files = {
        "statements": args.dir / "statements.csv",
        "pairs": args.dir / "pairs.csv",
        "manifest": args.dir / "manifest.json",
    }
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        fail(failures, "required_files", ", ".join(missing))
        for item in failures:
            print(item, file=sys.stderr)
        return 1

    statements = read_csv(files["statements"], STATEMENT_FIELDS, failures, "statements")
    pairs = read_csv(files["pairs"], PAIR_FIELDS, failures, "pairs")
    try:
        manifest = json.loads(files["manifest"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(failures, "manifest_read", str(exc))
        manifest = {}

    try:
        terms = load_terms(args.terms)
    except (OSError, KeyError, TypeError, json.JSONDecodeError, re.error) as exc:
        fail(failures, "terms_read", str(exc))
        terms = {}

    if manifest.get("release_status") != "fda_label_statements_not_clinically_reviewed":
        fail(failures, "release_status")

    headers_to_check = STATEMENT_FIELDS + PAIR_FIELDS
    if any(any(token in field.lower() for token in FORBIDDEN) for field in headers_to_check):
        fail(failures, "forbidden_column_name")
    if contains_forbidden(manifest):
        fail(failures, "forbidden_manifest_value")

    seen_ids: set[str] = set()
    calculated_pairs: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row_number, row in enumerate(statements, start=2):
        statement_id = row["statement_id"]
        expected_id = hashlib.sha1(
            f'{row["supplement_id"]}|{row["drug_id"]}|{row["sentence"]}'.encode("utf-8")
        ).hexdigest()[:16]
        if statement_id in seen_ids:
            fail(failures, "statement_id_unique", f"row {row_number}")
        seen_ids.add(statement_id)
        if statement_id != expected_id:
            fail(failures, "statement_id_recompute", f"row {row_number}")

        for field, expected in FIXED.items():
            if row[field] != expected:
                fail(failures, f"fixed_{field}", f"row {row_number}")

        entry = terms.get(row["supplement_id"])
        if entry is None:
            fail(failures, "supplement_id_exists", f"row {row_number}")
        else:
            match = entry["match"].search(row["sentence"])
            if match is None:
                fail(failures, "match_found", f"row {row_number}")
            elif match.group(0) != row["matched_text"]:
                fail(failures, "matched_text", f"row {row_number}")
            if any(pattern.search(row["sentence"]) for pattern in entry["exclude"]):
                fail(failures, "exclude_absent", f"row {row_number}")

        sentence = row["sentence"]
        if sentence != sentence.strip() or "  " in sentence or "\n" in sentence or "\r" in sentence:
            fail(failures, "sentence_whitespace", f"row {row_number}")
        if not UUID_RE.fullmatch(row["set_id"]):
            fail(failures, "set_id_uuid", f"row {row_number}")
        if not re.fullmatch(r"\d{8}", row["effective_time"]):
            fail(failures, "effective_time", f"row {row_number}")
        try:
            if int(row["label_count"]) < 1 or str(int(row["label_count"])) != row["label_count"]:
                raise ValueError
        except ValueError:
            fail(failures, "label_count", f"row {row_number}")

        # Added by Claude Code 2026-11-15: a "drug" with four or more ingredients is a vitamin product.
        if row["drug_id"].count("+") >= 3 or len(row["drug_id"]) > 80:
            fail(failures, "drug_id_multi_ingredient", f"row {row_number}")
        if row["drug_id"] == row["supplement_id"]:
            fail(failures, "pair_is_self", f"row {row_number}")

        calculated_pairs[(row["supplement_id"], row["drug_id"])].append(row)

    if isinstance(manifest, dict):
        if manifest.get("failed_requests"):
            fail(failures, "manifest_failed_requests")
        if re.search(r"[A-Za-z]:\\\\|/Users/|/home/", json.dumps(manifest)):
            fail(failures, "manifest_local_path")

    arguments =manifest.get("arguments") if isinstance(manifest, dict) else {}
    per_pair = arguments.get("per_pair") if isinstance(arguments, dict) else None
    if not isinstance(per_pair, int) or per_pair < 1:
        fail(failures, "manifest_per_pair")
    else:
        for pair, rows in calculated_pairs.items():
            if len(rows) > per_pair:
                fail(failures, "per_pair_limit", f"{pair!r}")

    pair_lookup: dict[tuple[str, str], dict[str, str]] = {}
    for row_number, row in enumerate(pairs, start=2):
        key = (row["supplement_id"], row["drug_id"])
        if key in pair_lookup:
            fail(failures, "pairs_unique", f"row {row_number}")
        pair_lookup[key] = row
        expected_rows = calculated_pairs.get(key, [])
        try:
            statements_count = int(row["statements"])
            labels_count = int(row["labels"])
        except ValueError:
            fail(failures, "pairs_integer", f"row {row_number}")
            continue
        if statements_count != len(expected_rows):
            fail(failures, "pairs_statements", f"row {row_number}")
        if labels_count != sum(int(item["label_count"]) for item in expected_rows):
            fail(failures, "pairs_labels", f"row {row_number}")
    if set(pair_lookup) != set(calculated_pairs):
        fail(failures, "pairs_agreement")

    counts = manifest.get("counts") if isinstance(manifest, dict) else {}
    expected_counts = {
        "statements": len(statements),
        "distinct_pairs": len(calculated_pairs),
        "distinct_supplements": len({row["supplement_id"] for row in statements}),
        "distinct_drugs": len({row["drug_id"] for row in statements}),
    }
    for field, expected in expected_counts.items():
        if counts.get(field) != expected:
            fail(failures, "manifest_counts", field)

    if failures:
        for item in failures:
            print(item, file=sys.stderr)
        return 1

    print(json.dumps({
        "VALID": True,
        "statements": len(statements),
        "pairs": len(pairs),
        "supplements": len({row["supplement_id"] for row in statements}),
        "drugs": len({row["drug_id"] for row in statements}),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
