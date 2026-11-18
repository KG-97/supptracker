#!/usr/bin/env python3
"""Repair statements that run from one label-table row into the next (see scripts/label_text.py).

Added by Claude Code 2026-11-18. For each statement matching ``CROSSED_ROWS_RE`` it fetches the cited label
from openFDA, splits the drug-interaction text with ``label_text.split_units`` and replaces the sentence with
the matched row's own text. A statement that cannot be repaired exactly is dropped (fail closed). The new
sentence must be a verbatim substring of the label text, pass the dictionary's match and exclude rules and fit
the length limit. label_count is kept: it counts the labels that carried the original passage, whose rows are
the same text. pairs.csv and the manifest counts are recomputed.

Usage: python scripts/repair_crossed_rows.py [--dir data/openfda_supplement_statements] [--write]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from label_text import CROSSED_ROWS_RE, examples_statement, split_units  # noqa: E402

MAX_CHARS = 1300  # a whole table row; plain sentences keep the builder's 700 limit


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "SuppTracker-openfda-statements/1.0"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.load(response)
            results = payload.get("results") or []
            items = results[0].get("drug_interactions") or [] if results else []
            return compact(" ".join(item for item in items if isinstance(item, str)))
        except Exception:  # noqa: BLE001 - retried, then reported
            time.sleep(2 + 2 * attempt)
    raise RuntimeError(f"could not fetch {url}")


def statement_id(row: dict[str, str]) -> str:
    key = f'{row["supplement_id"]}|{row["drug_id"]}|{row["sentence"]}'
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def repair(row: dict[str, str], text: str, entry: dict) -> tuple[str, str] | None:
    """Return (sentence, matched_text) for the row's own table row, or None."""
    old = row["sentence"]
    if old not in text:
        return None
    cut = old.find(row["matched_text"])
    if cut < 0:
        return None
    prefix = old[: cut + len(row["matched_text"])]
    for unit in split_units(text):
        if unit.kind != "examples" or prefix not in unit.text[unit.list_start :]:
            continue
        for match in entry["match"].finditer(unit.text, unit.list_start):
            sentence = examples_statement(unit, match.start(), match.end())
            if sentence is None or sentence not in text or len(sentence) > MAX_CHARS:
                continue
            if any(pattern.search(sentence) for pattern in entry["exclude"]):
                continue
            if CROSSED_ROWS_RE.search(sentence):
                continue
            return sentence, match.group(0)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path("data/openfda_supplement_statements"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    statements_path = args.dir / "statements.csv"
    with statements_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    terms = json.loads((args.dir / "supplement_terms.json").read_text(encoding="utf-8"))
    entries = {
        str(item["id"]): {
            "match": re.compile(str(item["match"]), re.IGNORECASE),
            "exclude": [re.compile(str(pattern), re.IGNORECASE) for pattern in item.get("exclude", [])],
        }
        for item in terms["entries"]
    }

    texts: dict[str, str] = {}
    kept: list[dict[str, str]] = []
    report = {"crossed": 0, "repaired": 0, "dropped": 0, "merged": 0, "changes": []}
    for row in rows:
        if not CROSSED_ROWS_RE.search(row["sentence"]):
            kept.append(row)
            continue
        report["crossed"] += 1
        url = row["source_url"]
        if url not in texts:
            texts[url] = fetch_text(url)
            time.sleep(0.5)
        fixed = repair(row, texts[url], entries[row["supplement_id"]])
        change = {"supplement_id": row["supplement_id"], "drug_id": row["drug_id"], "old": row["sentence"]}
        if fixed is None:
            report["dropped"] += 1
            change["new"] = None
        else:
            report["repaired"] += 1
            new_row = dict(row, sentence=fixed[0], matched_text=fixed[1])
            new_row["statement_id"] = statement_id(new_row)
            change["new"] = fixed[0]
            kept.append(new_row)
        report["changes"].append(change)

    # Two old passages can repair to the same row text: keep one row and add up the labels.
    merged: dict[tuple[str, str, str], dict[str, str]] = {}
    ordered: list[dict[str, str]] = []
    for row in kept:
        key = (row["supplement_id"], row["drug_id"], row["sentence"])
        if key in merged:
            first = merged[key]
            first["label_count"] = str(int(first["label_count"]) + int(row["label_count"]))
            if (row["effective_time"], row["set_id"]) > (first["effective_time"], first["set_id"]):
                for field in ("set_id", "label_id", "effective_time", "source_url", "matched_text"):
                    first[field] = row[field]
            report["merged"] += 1
            continue
        merged[key] = row
        ordered.append(row)
    ordered.sort(key=lambda item: (item["supplement_id"], item["drug_id"], -int(item["label_count"]), item["sentence"]))

    pairs: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in ordered:
        pairs[(row["supplement_id"], row["drug_id"])].append(row)

    print(json.dumps({key: value for key, value in report.items() if key != "changes"}))
    for change in report["changes"]:
        print(f'\n[{change["supplement_id"]} + {change["drug_id"]}]\n  OLD: {change["old"]}\n  NEW: {change["new"]}')
    if not args.write:
        print("\n(dry run: nothing written; pass --write)")
        return 0
    if not report["crossed"]:
        print("nothing to repair; nothing written")
        return 0

    with statements_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ordered)
    with (args.dir / "pairs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["supplement_id", "drug_id", "statements", "labels"], lineterminator="\n")
        writer.writeheader()
        for (supplement_id, drug_id), items in sorted(pairs.items()):
            writer.writerow({
                "supplement_id": supplement_id,
                "drug_id": drug_id,
                "statements": len(items),
                "labels": sum(int(item["label_count"]) for item in items),
            })
    manifest_path = args.dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"].update({
        "statements": len(ordered),
        "distinct_pairs": len(pairs),
        "distinct_supplements": len({row["supplement_id"] for row in ordered}),
        "distinct_drugs": len({row["drug_id"] for row in ordered}),
    })
    runs = manifest.get("row_repairs")
    runs = runs if isinstance(runs, list) else []
    runs.append({
        "date": datetime.now(timezone.utc).date().isoformat(),
        "script": "scripts/repair_crossed_rows.py",
        "crossed_rows_found": report["crossed"],
        "repaired": report["repaired"],
        "dropped": report["dropped"],
        "merged": report["merged"],
        "note": "Statements that ran from one table row into the next were cut back to their own row; "
        "label_count counts the labels that carried the original passage.",
    })
    manifest["row_repairs"] = runs
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
