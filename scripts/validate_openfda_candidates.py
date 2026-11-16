"""Validate the isolated openFDA label-candidate corpus.

This validator intentionally accepts only candidate-review fields.  It rejects
clinical assertion columns so label text cannot silently become scored evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    from .substance_identity import is_same_substance
except ImportError:
    from substance_identity import is_same_substance


COMPOUND_FIELDS = ["id", "name", "synonyms", "class", "route", "dose", "source"]
CANDIDATE_FIELDS = [
    "candidate_id", "record_kind", "review_status", "subject_compound_id",
    "mentioned_compound_id", "mentioned_text", "section", "source_id", "set_id",
    "effective_time", "source_url", "extracted_text", "extraction_method",
    "retrieved_at", "rights_status",
]
SOURCE_FIELDS = ["id", "title", "citation", "identifier", "date", "extra"]
FORBIDDEN_CANDIDATE_COLUMNS = {
    "risk", "severity", "evidence", "mechanism", "effect", "action",
    "risk_level", "risk_score", "bidirectional", "assessment",
}


def read_csv(path: Path, required_fields: list[str], errors: list[str]) -> list[dict[str, str]]:
    if not path.is_file():
        errors.append(f"missing file: {path}")
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if fieldnames != required_fields:
            errors.append(f"{path.name}: expected exact headers {required_fields}; got {fieldnames}")
        return list(reader)


def validate(dataset: Path, min_compounds: int, min_candidates: int, min_pairs: int) -> list[str]:
    errors: list[str] = []
    compounds = read_csv(dataset / "compounds.csv", COMPOUND_FIELDS, errors)
    candidates = read_csv(dataset / "label_candidates.csv", CANDIDATE_FIELDS, errors)
    sources = read_csv(dataset / "sources.csv", SOURCE_FIELDS, errors)
    compound_ids = {row.get("id", "").strip() for row in compounds if row.get("id", "").strip()}
    source_ids = {row.get("id", "").strip() for row in sources if row.get("id", "").strip()}
    if len(compound_ids) != len(compounds):
        errors.append("compounds.csv contains blank or duplicate ids")
    if len(compound_ids) < min_compounds:
        errors.append(f"need at least {min_compounds} distinct compounds; found {len(compound_ids)}")
    candidate_ids: set[str] = set()
    candidate_pairs: set[tuple[str, str]] = set()
    for number, row in enumerate(candidates, start=2):
        identifier = row.get("candidate_id", "").strip()
        if not identifier or identifier in candidate_ids:
            errors.append(f"label_candidates.csv:{number}: blank or duplicate candidate_id")
        candidate_ids.add(identifier)
        if row.get("record_kind") != "openfda_label_candidate":
            errors.append(f"label_candidates.csv:{number}: invalid record_kind")
        if row.get("review_status") not in {"unreviewed", "rejected"}:
            errors.append(f"label_candidates.csv:{number}: invalid review_status")
        subject = row.get("subject_compound_id", "").strip()
        mentioned = row.get("mentioned_compound_id", "").strip()
        if not subject or subject == mentioned or subject not in compound_ids or mentioned not in compound_ids:
            errors.append(f"label_candidates.csv:{number}: invalid compound references")
        elif is_same_substance(subject, mentioned):
            errors.append(f"label_candidates.csv:{number}: same-substance candidate pair")
        candidate_pairs.add((subject, mentioned))
        if row.get("source_id", "").strip() not in source_ids:
            errors.append(f"label_candidates.csv:{number}: unknown source_id")
        if row.get("section") != "DRUG INTERACTIONS" or not row.get("set_id", "").strip():
            errors.append(f"label_candidates.csv:{number}: missing label section or set id")
        if not row.get("source_url", "").startswith("https://api.fda.gov/"):
            errors.append(f"label_candidates.csv:{number}: source_url must be an openFDA HTTPS URL")
        if not row.get("extracted_text", "").strip() or row.get("extraction_method") != "generic_name_exact_match_v1":
            errors.append(f"label_candidates.csv:{number}: missing excerpt or unsupported extraction method")
        if row.get("rights_status") != "cc0_unless_otherwise_noted":
            errors.append(f"label_candidates.csv:{number}: invalid rights_status")
    if len(candidate_ids) < min_candidates:
        errors.append(f"need at least {min_candidates} candidate records; found {len(candidate_ids)}")
    if len(candidate_pairs) < min_pairs:
        errors.append(f"need at least {min_pairs} distinct directed candidate pairs; found {len(candidate_pairs)}")
    for row in sources:
        try:
            extra = json.loads(row.get("extra") or "{}")
        except json.JSONDecodeError:
            errors.append(f"sources.csv:{row.get('id')}: extra is not JSON")
            continue
        if extra.get("license_url") != "https://open.fda.gov/license/":
            errors.append(f"sources.csv:{row.get('id')}: missing openFDA licence URL")
        if extra.get("license") != "CC0-1.0 unless otherwise noted by openFDA":
            errors.append(f"sources.csv:{row.get('id')}: missing qualified licence statement")
    manifest_path = dataset / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid manifest.json: {exc}")
        manifest = {}
    if manifest.get("release_status") != "candidate_only_not_clinically_validated":
        errors.append("manifest must declare candidate_only_not_clinically_validated")
    if manifest.get("source", {}).get("license_url") != "https://open.fda.gov/license/":
        errors.append("manifest must cite the openFDA licence")
    skipped_count = manifest.get("counts", {}).get("same_substance_candidate_rows_skipped")
    if type(skipped_count) is not int or skipped_count < 0:
        errors.append("manifest must contain a non-negative same_substance_candidate_rows_skipped count")
        skipped_count = None
    expected_counts = {
        "compounds": len(compound_ids),
        "candidates": len(candidate_ids),
        "distinct_directed_candidate_pairs": len(candidate_pairs),
        "sources": len(source_ids),
        "same_substance_candidate_rows_skipped": skipped_count,
    }
    if manifest.get("counts") != expected_counts:
        errors.append(f"manifest counts do not match corpus: expected {expected_counts}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/openfda_candidates"))
    parser.add_argument("--min-compounds", type=int, default=1000)
    parser.add_argument("--min-candidates", type=int, default=1000)
    parser.add_argument("--min-distinct-pairs", type=int, default=1000)
    args = parser.parse_args()
    errors = validate(args.dataset, args.min_compounds, args.min_candidates, args.min_distinct_pairs)
    if errors:
        print("INVALID openFDA candidate corpus:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("VALID openFDA candidate corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
