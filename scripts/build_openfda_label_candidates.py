#!/usr/bin/env python3
"""Build an auditable *candidate* interaction corpus from openFDA labels.

This script deliberately does not infer clinical severity or declare an
interaction to be established.  It finds pairs where one label's DRUG
INTERACTIONS text explicitly mentions the generic name of another labelled
product, and records the source label required for human review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from .substance_identity import is_same_substance
except ImportError:
    from substance_identity import is_same_substance


API_URL = "https://api.fda.gov/drug/label.json"
QUERY = "drug_interactions:* AND openfda.generic_name:*"
LICENSE_URL = "https://open.fda.gov/license/"
SOURCE_KIND = "openFDA label-derived interaction candidate"


def canonical_id(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def normalise_name(value: str) -> str:
    return " ".join(value.strip().split())


def token_key(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.lower()))


def generic_names(record: dict[str, Any]) -> Iterable[str]:
    openfda = record.get("openfda") or {}
    for field in ("generic_name", "substance_name"):
        for raw_value in openfda.get(field) or []:
            if not isinstance(raw_value, str):
                continue
            value = normalise_name(raw_value)
            if 3 <= len(value) <= 96 and re.search(r"[A-Za-z]", value):
                yield value


def get_page(skip: int, limit: int) -> list[dict[str, Any]]:
    query = urlencode({"search": QUERY, "limit": limit, "skip": skip})
    request = Request(f"{API_URL}?{query}", headers={"User-Agent": "SuppTracker-openFDA-candidate-builder/1.0"})
    with urlopen(request, timeout=60) as response:  # nosec B310 - fixed FDA endpoint
        payload = json.load(response)
    return payload.get("results") or []


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def source_url(set_id: str) -> str:
    return f'{API_URL}?{urlencode({"search": f"set_id:\"{set_id}\"", "limit": 1})}'


def excerpt_for(text: str, match_start: int, match_end: int, radius: int = 420) -> str:
    start = max(0, match_start - radius)
    end = min(len(text), match_end + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return prefix + compact_text(text[start:end]) + suffix


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build(output_dir: Path, pages: int, page_size: int, max_candidates: int, sleep_seconds: float) -> dict[str, int]:
    records: list[dict[str, Any]] = []
    for page in range(pages):
        page_records = get_page(page * page_size, page_size)
        if not page_records:
            break
        records.extend(page_records)
        if len(page_records) < page_size:
            break
        if sleep_seconds:
            time.sleep(sleep_seconds)

    compounds: dict[str, dict[str, str]] = {}
    names_to_ids: dict[tuple[str, ...], set[str]] = defaultdict(set)
    names_by_first_token: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    record_subjects: list[tuple[dict[str, Any], list[str], str]] = []
    for record in records:
        subjects: list[str] = []
        for raw_name in generic_names(record):
            compound_id = canonical_id(raw_name)
            if not compound_id:
                continue
            subjects.append(compound_id)
            name_key = token_key(raw_name)
            if not name_key:
                continue
            if name_key not in names_to_ids:
                names_by_first_token[name_key[0]].append(name_key)
            names_to_ids[name_key].add(compound_id)
            compounds.setdefault(
                compound_id,
                {
                    "id": compound_id,
                    "name": raw_name,
                    "synonyms": "",
                    "class": "FDA-labelled drug or substance",
                    "route": "",
                    "dose": "",
                    "source": "openFDA product label",
                },
            )
        text = compact_text(" ".join(record.get("drug_interactions") or []))
        if subjects and text:
            record_subjects.append((record, list(dict.fromkeys(subjects)), text))

    for keys in names_by_first_token.values():
        keys.sort(key=lambda value: (-len(value), value))
    candidates: dict[tuple[str, str, str], dict[str, str]] = {}
    skipped_candidate_keys: set[tuple[str, str, str]] = set()
    same_substance_candidate_rows_skipped = 0
    sources: dict[str, dict[str, str]] = {}
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for record, subjects, text in record_subjects:
        set_id = str(record.get("set_id") or record.get("id") or "").strip()
        if not set_id:
            continue
        text_tokens = list(re.finditer(r"[A-Za-z0-9]+", text.lower()))
        token_values = [token.group(0) for token in text_tokens]
        for index, token in enumerate(token_values):
            for name_key in names_by_first_token.get(token, []):
                end_index = index + len(name_key)
                if tuple(token_values[index:end_index]) != name_key:
                    continue
                match_start = text_tokens[index].start()
                match_end = text_tokens[end_index - 1].end()
                for counterpart_id in names_to_ids[name_key]:
                    for subject_id in subjects:
                        candidate_key = (subject_id, counterpart_id, set_id)
                        if candidate_key in candidates or candidate_key in skipped_candidate_keys:
                            continue
                        if is_same_substance(subject_id, counterpart_id):
                            skipped_candidate_keys.add(candidate_key)
                            same_substance_candidate_rows_skipped += 1
                            continue
                        source_id = f"openfda:{set_id}"
                        source_text = text
                        sources[source_id] = {
                        "id": source_id,
                        "title": f"openFDA product label {set_id}",
                        "citation": "FDA Structured Product Labeling, DRUG INTERACTIONS section (label-derived candidate; not clinical validation)",
                        "identifier": set_id,
                        "date": str(record.get("effective_time") or ""),
                        "extra": json.dumps(
                            {
                                "url": source_url(set_id),
                                "label_id": record.get("id"),
                                "license": "CC0-1.0 unless otherwise noted by openFDA",
                                "license_url": LICENSE_URL,
                                "retrieved_at": retrieved_at,
                                "drug_interactions_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                            },
                            sort_keys=True,
                        ),
                    }
                        candidates[candidate_key] = {
                        "candidate_id": f"openfda:{subject_id}:{counterpart_id}:{set_id}",
                        "record_kind": "openfda_label_candidate",
                        "review_status": "unreviewed",
                        "subject_compound_id": subject_id,
                        "mentioned_compound_id": counterpart_id,
                        "mentioned_text": compounds[counterpart_id]["name"],
                        "section": "DRUG INTERACTIONS",
                        "source_id": source_id,
                        "set_id": set_id,
                        "effective_time": str(record.get("effective_time") or ""),
                        "source_url": source_url(set_id),
                        "extracted_text": excerpt_for(text, match_start, match_end),
                        "extraction_method": "generic_name_exact_match_v1",
                        "retrieved_at": retrieved_at,
                        "rights_status": "cc0_unless_otherwise_noted",
                    }
                        if len(candidates) >= max_candidates:
                            break
                if len(candidates) >= max_candidates:
                    break
            if len(candidates) >= max_candidates:
                break
        if len(candidates) >= max_candidates:
            break

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "compounds.csv", ["id", "name", "synonyms", "class", "route", "dose", "source"], sorted(compounds.values(), key=lambda item: item["id"]))
    write_csv(output_dir / "label_candidates.csv", ["candidate_id", "record_kind", "review_status", "subject_compound_id", "mentioned_compound_id", "mentioned_text", "section", "source_id", "set_id", "effective_time", "source_url", "extracted_text", "extraction_method", "retrieved_at", "rights_status"], sorted(candidates.values(), key=lambda item: item["candidate_id"]))
    write_csv(output_dir / "sources.csv", ["id", "title", "citation", "identifier", "date", "extra"], sorted(sources.values(), key=lambda item: item["id"]))
    manifest = {
        "schema_version": 1,
        "dataset_name": "SuppTracker openFDA label-derived candidates",
        "release_status": "candidate_only_not_clinically_validated",
        "source": {
            "name": "openFDA drug product labeling API",
            "query": QUERY,
            "api_url": API_URL,
            "license": "CC0-1.0 unless otherwise noted by openFDA",
            "license_url": LICENSE_URL,
            "retrieved_at": retrieved_at,
        },
        "extraction": {
            "script": "scripts/build_openfda_label_candidates.py",
            "pages_requested": pages,
            "page_size": page_size,
            "source_records_retrieved": len(records),
            "candidate_rule": "A labelled generic/substance name is mentioned in another label's DRUG INTERACTIONS text.",
            "same_substance_exclusion_rule": "Exclude a pair when both identifiers normalize to the same active substance or one is an ingredient of the other explicit combination product.",
            "clinical_claim": "None. Every candidate requires human/clinical review before risk scoring or display as an assessed interaction.",
        },
        "counts": {
            "compounds": len(compounds),
            "candidates": len(candidates),
            "distinct_directed_candidate_pairs": len({(row["subject_compound_id"], row["mentioned_compound_id"]) for row in candidates.values()}),
            "sources": len(sources),
            "same_substance_candidate_rows_skipped": same_substance_candidate_rows_skipped,
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest["counts"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/openfda_candidates"))
    parser.add_argument("--pages", type=int, default=12)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-candidates", type=int, default=5000)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--min-compounds", type=int, default=1000)
    parser.add_argument("--min-candidates", type=int, default=1000)
    parser.add_argument("--min-distinct-pairs", type=int, default=1000)
    args = parser.parse_args()
    if args.pages < 1 or not 1 <= args.page_size <= 1000 or args.max_candidates < 1:
        parser.error("pages and max-candidates must be positive; page-size must be 1..1000")
    counts = build(args.output_dir, args.pages, args.page_size, args.max_candidates, args.sleep_seconds)
    print(json.dumps(counts, sort_keys=True))
    if (counts["compounds"] < args.min_compounds or counts["candidates"] < args.min_candidates
            or counts["distinct_directed_candidate_pairs"] < args.min_distinct_pairs):
        print("ERROR: corpus did not meet requested minimum counts", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
