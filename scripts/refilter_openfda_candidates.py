#!/usr/bin/env python3
"""Remove same-substance rows from an existing openFDA candidate corpus."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

try:
    from .substance_identity import is_same_substance
except ImportError:
    from substance_identity import is_same_substance


COMPOUND_FILE = "compounds.csv"
CANDIDATE_FILE = "label_candidates.csv"
SOURCE_FILE = "sources.csv"
MANIFEST_FILE = "manifest.json"
SKIPPED_COUNT_KEY = "same_substance_candidate_rows_skipped"


def read_raw_csv(path: Path) -> tuple[bytes, list[tuple[bytes, dict[str, str]]]]:
    with path.open("rb") as handle:
        lines = handle.readlines()
    if not lines:
        raise ValueError(f"{path}: empty CSV")

    try:
        header_values = next(csv.reader([lines[0].decode("utf-8")]))
    except (UnicodeDecodeError, StopIteration, csv.Error) as exc:
        raise ValueError(f"{path}: invalid CSV header") from exc

    rows: list[tuple[bytes, dict[str, str]]] = []
    for number, raw_line in enumerate(lines[1:], start=2):
        try:
            values = next(csv.reader([raw_line.decode("utf-8")]))
        except (UnicodeDecodeError, StopIteration, csv.Error) as exc:
            raise ValueError(f"{path}:{number}: invalid CSV row") from exc
        if len(values) != len(header_values):
            raise ValueError(f"{path}:{number}: unexpected column count")
        rows.append((raw_line, dict(zip(header_values, values))))
    return lines[0], rows


def write_raw_csv_temporary(path: Path, header: bytes, rows: list[tuple[bytes, dict[str, str]]]) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temporary = Path(handle.name)
        handle.write(header)
        for raw_line, _ in rows:
            handle.write(raw_line)
        handle.flush()
        os.fsync(handle.fileno())
    return temporary


def write_text_temporary(path: Path, text: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return temporary


def candidate_pairs(rows: list[tuple[bytes, dict[str, str]]]) -> set[tuple[str, str]]:
    return {
        (row["subject_compound_id"], row["mentioned_compound_id"])
        for _, row in rows
    }


def refilter(dataset: Path, dry_run: bool) -> dict[str, int]:
    candidate_path = dataset / CANDIDATE_FILE
    source_path = dataset / SOURCE_FILE
    manifest_path = dataset / MANIFEST_FILE

    candidate_header, candidates = read_raw_csv(candidate_path)
    source_header, sources = read_raw_csv(source_path)
    compound_header, compounds = read_raw_csv(dataset / COMPOUND_FILE)
    del compound_header  # Compounds intentionally retain the build's full label dictionary.

    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{manifest_path}: invalid manifest") from exc

    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise ValueError(f"{manifest_path}: counts must be an object")
    prior_skipped = counts.get(SKIPPED_COUNT_KEY, 0)
    if type(prior_skipped) is not int or prior_skipped < 0:
        raise ValueError(f"{manifest_path}: {SKIPPED_COUNT_KEY} must be a non-negative integer")

    kept_candidates = [
        item
        for item in candidates
        if not is_same_substance(
            item[1]["subject_compound_id"],
            item[1]["mentioned_compound_id"],
        )
    ]
    used_source_ids = {row["source_id"] for _, row in kept_candidates}
    kept_sources = [item for item in sources if item[1]["id"] in used_source_ids]

    rows_removed = len(candidates) - len(kept_candidates)
    sources_removed = len(sources) - len(kept_sources)
    remaining_compound_ids = {row["id"] for _, row in compounds}
    referenced_compound_ids = {
        compound_id
        for _, row in kept_candidates
        for compound_id in (row["subject_compound_id"], row["mentioned_compound_id"])
    }
    compounds_removed = 0
    if not referenced_compound_ids.issubset(remaining_compound_ids):
        raise ValueError(f"{dataset}: kept candidates reference unknown compounds")

    manifest["counts"] = {
        "compounds": len(compounds),
        "candidates": len(kept_candidates),
        "distinct_directed_candidate_pairs": len(candidate_pairs(kept_candidates)),
        "sources": len(kept_sources),
        SKIPPED_COUNT_KEY: prior_skipped + rows_removed,
    }
    new_manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    summary = {
        "rows_before": len(candidates),
        "rows_after": len(kept_candidates),
        "pairs_before": len(candidate_pairs(candidates)),
        "pairs_after": len(candidate_pairs(kept_candidates)),
        "rows_removed": rows_removed,
        "compounds_removed": compounds_removed,
        "sources_removed": sources_removed,
    }

    if dry_run:
        return summary

    temporary_files: list[tuple[Path, Path]] = []
    try:
        if rows_removed:
            temporary_files.append(
                (
                    candidate_path,
                    write_raw_csv_temporary(candidate_path, candidate_header, kept_candidates),
                )
            )
        if sources_removed:
            temporary_files.append(
                (
                    source_path,
                    write_raw_csv_temporary(source_path, source_header, kept_sources),
                )
            )
        if new_manifest_text != manifest_text:
            temporary_files.append((manifest_path, write_text_temporary(manifest_path, new_manifest_text)))

        for destination, temporary in temporary_files:
            os.replace(temporary, destination)
    except Exception:
        for _, temporary in temporary_files:
            temporary.unlink(missing_ok=True)
        raise
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path("data/openfda_candidates"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(refilter(args.dir, args.dry_run), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
