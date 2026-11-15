#!/usr/bin/env python3
"""Build verbatim supplement mentions from openFDA label interaction text."""

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
from typing import Any
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.fda.gov/drug/label.json"
LICENSE_URL = "https://open.fda.gov/license/"
MAX_DRUG_COMPONENTS = 3
MAX_DRUG_ID_CHARS = 80
CACHE_TIMES: list[float] = []  # when each page used from the cache was first downloaded
SALT_WORDS = {
    "hydrochloride", "dihydrochloride", "hydrobromide", "sodium", "potassium",
    "calcium", "magnesium", "sulfate", "bisulfate", "maleate", "tartrate",
    "bitartrate", "mesylate", "besylate", "tosylate", "fumarate", "succinate",
    "citrate", "acetate", "phosphate", "nitrate", "bromide", "chloride",
    "lactate", "gluconate", "pamoate", "olamine", "hemihydrate", "monohydrate",
    "dihydrate", "anhydrous",
}
STATEMENT_FIELDS = [
    "statement_id", "record_kind", "review_status", "supplement_id",
    "supplement_name", "supplement_kind", "drug_id", "drug_names_raw",
    "sentence", "matched_text", "section", "set_id", "label_id",
    "effective_time", "label_count", "source_url", "retrieved_at",
    "rights_status",
]
PAIR_FIELDS = ["supplement_id", "drug_id", "statements", "labels"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9+]+", "-", value.lower()).strip("-")


def normalized_substance(value: str) -> str:
    value = compact(value).lower()
    words = value.split()
    if not words or words[0] in SALT_WORDS:
        return value
    while len(words) > 1 and words[-1] in SALT_WORDS:
        words.pop()
    return " ".join(words)


_QUOTE_VARIANTS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "‑": "-"})
_BULLETS_RE = re.compile(r"[•·◦▪■●*]")


def near_duplicate_key(sentence: str) -> str:
    """Key that is equal for sentences differing only in case, spacing, bullets or quote style.

    Deliberately narrow: digits, full stops, commas, arrows and comparison signs stay significant,
    so "2.5 mg" never merges with "25 mg" and an up arrow never merges with a down arrow.
    """

    value = _BULLETS_RE.sub(" ", sentence.translate(_QUOTE_VARIANTS)).casefold()
    value = re.sub(r"\s+", " ", value).strip()
    # A space next to a symbol carries no meaning ("↓ atazanavir" and "↓atazanavir").
    return re.sub(r"(?<=[^\w\s]) | (?=[^\w\s])", "", value)


def label_source_url(set_id: str) -> str:
    query = urlencode({"search": f'set_id:"{set_id}"', "limit": 1})
    return f"{API_URL}?{query}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)


def load_entries(path: Path, only: str | None) -> list[dict[str, Any]]:
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read dictionary: {exc}") from exc
    if not isinstance(source, dict) or not isinstance(source.get("entries"), list):
        raise ValueError('dictionary must contain an "entries" list')

    wanted = None
    if only:
        wanted = {item.strip() for item in only.split(",") if item.strip()}
        if not wanted:
            raise ValueError("--only must contain at least one id")

    entries: list[dict[str, Any]] = []
    known_ids: set[str] = set()
    for index, raw in enumerate(source["entries"]):
        if not isinstance(raw, dict):
            raise ValueError(f"dictionary entry {index} is not an object")
        entry_id = raw.get("id")
        name = raw.get("name")
        kind = raw.get("kind")
        phrases = raw.get("search")
        match = raw.get("match")
        if not all(isinstance(item, str) and item.strip() for item in (entry_id, name, kind, match)):
            raise ValueError(f"dictionary entry {index} needs non-empty id, name, kind, and match")
        if entry_id in known_ids:
            raise ValueError(f"duplicate dictionary entry id: {entry_id}")
        known_ids.add(entry_id)
        if not isinstance(phrases, list) or not phrases or not all(isinstance(item, str) and item.strip() for item in phrases):
            raise ValueError(f"dictionary entry {entry_id} needs a non-empty search list")
        exclude = raw.get("exclude", [])
        self_patterns = raw.get("self", [])
        if not isinstance(exclude, list) or not all(isinstance(item, str) for item in exclude):
            raise ValueError(f"dictionary entry {entry_id} has an invalid exclude list")
        if not isinstance(self_patterns, list) or not all(isinstance(item, str) for item in self_patterns):
            raise ValueError(f"dictionary entry {entry_id} has an invalid self list")
        try:
            compiled_match = re.compile(match, re.IGNORECASE)
            compiled_exclude = [re.compile(item, re.IGNORECASE) for item in exclude]
            compiled_self = [re.compile(item, re.IGNORECASE) for item in self_patterns]
        except re.error as exc:
            raise ValueError(f"dictionary entry {entry_id} has an invalid regex: {exc}") from exc
        if wanted is None or entry_id in wanted:
            entries.append({
                "id": entry_id,
                "name": name,
                "kind": kind,
                "search": phrases,
                "match_re": compiled_match,
                "exclude_re": compiled_exclude,
                "self_re": compiled_self,
            })

    if wanted:
        missing = sorted(wanted - known_ids)
        if missing:
            raise ValueError("--only contains unknown id(s): " + ", ".join(missing))
    if not entries:
        raise ValueError("no dictionary entries selected")
    return entries


def fetch_page(
    phrase: str,
    skip: int,
    page_size: int,
    sleep_seconds: float,
    failures: list[dict[str, Any]],
    entry_stats: dict[str, Any],
    cache_dir: Path | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    query = urlencode({
        "search": f'drug_interactions:"{phrase}"',
        "limit": page_size,
        "skip": skip,
    })
    url = f"{API_URL}?{query}"

    # Page cache and wider retries added by Claude Code 2026-11-15: the first full run died on an
    # uncaught http.client.IncompleteRead after 39 pages (each page is about 19 MB). A cached page keeps
    # only the fields the build reads, so a restart continues instead of downloading everything again.
    cache_file: Path | None = None
    if cache_dir is not None:
        key = hashlib.sha1(f"{phrase}|{page_size}|{skip}".encode("utf-8")).hexdigest()
        cache_file = cache_dir / f"{key}.json"
        if cache_file.is_file():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                if cached.get("cache_phrase") == phrase and cached.get("cache_skip") == skip:
                    CACHE_TIMES.append(cache_file.stat().st_mtime)
                    entry_stats["cached_pages"] = entry_stats.get("cached_pages", 0) + 1
                    if cached.get("not_found"):
                        return None, True
                    return cached, False
            except (OSError, ValueError):
                pass  # unreadable cache entry: fetch again

    def keep(payload: dict[str, Any] | None, not_found: bool) -> None:
        if cache_file is None:
            return
        slim: dict[str, Any] = {"cache_phrase": phrase, "cache_skip": skip, "not_found": not_found}
        if payload is not None:
            slim["meta"] = payload.get("meta")
            slim["results"] = [
                {
                    "id": label.get("id"),
                    "set_id": label.get("set_id"),
                    "effective_time": label.get("effective_time"),
                    "drug_interactions": label.get("drug_interactions"),
                    "openfda": {
                        "substance_name": (label.get("openfda") or {}).get("substance_name"),
                        "generic_name": (label.get("openfda") or {}).get("generic_name"),
                    },
                }
                for label in (payload.get("results") or [])
                if isinstance(label, dict)
            ]
        temp = cache_file.with_suffix(".tmp")
        temp.write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")
        temp.replace(cache_file)

    attempts = 8
    for attempt in range(attempts):
        entry_stats["requests"] += 1
        print(f"request phrase={phrase!r} skip={skip} attempt={attempt + 1}", file=sys.stderr, flush=True)
        try:
            request = Request(url, headers={"User-Agent": "SuppTracker-openfda-statements/1.0"})
            with urlopen(request, timeout=180) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise json.JSONDecodeError("top level is not an object", "", 0)
            keep(payload, False)
            return payload, False
        except HTTPError as exc:
            if exc.code == 404:
                keep(None, True)
                return None, True
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            detail = f"HTTP {exc.code}"
        except (TimeoutError, URLError, HTTPException, ConnectionError, json.JSONDecodeError) as exc:
            # A cut-off body shows up as IncompleteRead (an HTTPException) or as broken JSON.
            retryable = True
            detail = f"{type(exc).__name__}: {exc}"[:300]
        except OSError as exc:
            retryable = False
            detail = str(exc) or type(exc).__name__

        if retryable and attempt < attempts - 1:
            time.sleep(min(60.0, max(sleep_seconds, 0.1) + 2.0 ** attempt))
            continue
        failures.append({
            "phrase": phrase,
            "skip": skip,
            "url": url,
            "error": detail,
        })
        return None, False
    return None, False


def build(args: argparse.Namespace) -> dict[str, int]:
    started_at = utc_now()
    entries = load_entries(args.terms, args.only)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.cache_dir is not None:
        args.cache_dir.mkdir(parents=True, exist_ok=True)

    entry_stats: dict[str, dict[str, Any]] = {
        entry["id"]: {
            "requests": 0,
            "hits_reported_by_api": 0,
            "labels_scanned_first_by_this_entry": 0,
            "statements": 0,
            "pairs": 0,
        }
        for entry in entries
    }
    scanned_ids: set[str] = set()
    aggregates: dict[tuple[str, str, str], dict[str, Any]] = {}
    truncations: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    meta_updated: set[str] = set()
    counts = {
        "labels_scanned": 0,
        "labels_without_drug_identity": 0,
        "labels_multi_ingredient_skipped": 0,
        "statements": 0,
        "distinct_pairs": 0,
        "distinct_supplements": 0,
        "distinct_drugs": 0,
        "sentences_too_long": 0,
        "self_skips": 0,
        "near_duplicate_sentences_merged": 0,
    }

    for finder_entry in entries:
        stats = entry_stats[finder_entry["id"]]
        for phrase in finder_entry["search"]:
            skip = 0
            pages = 0
            total: int | None = None
            while True:
                if skip > 25000:
                    truncations.append({
                        "supplement_id": finder_entry["id"],
                        "phrase": phrase,
                        "reason": "skip_would_exceed_25000",
                        "skip": skip,
                    })
                    break
                if args.max_pages and pages >= args.max_pages:
                    truncations.append({
                        "supplement_id": finder_entry["id"],
                        "phrase": phrase,
                        "reason": "max_pages",
                        "skip": skip,
                    })
                    break

                payload, not_found = fetch_page(
                    phrase, skip, args.page_size, args.sleep_seconds, failures, stats, args.cache_dir,
                )
                pages += 1
                if not_found or payload is None:
                    break

                meta = payload.get("meta") if isinstance(payload, dict) else {}
                results_meta = meta.get("results") if isinstance(meta, dict) else {}
                if isinstance(meta, dict) and meta.get("last_updated") is not None:
                    meta_updated.add(str(meta["last_updated"]))
                try:
                    page_total = int(results_meta.get("total", 0))
                except (TypeError, ValueError):
                    page_total = 0
                if total is None:
                    total = page_total
                    stats["hits_reported_by_api"] += page_total

                results = payload.get("results") if isinstance(payload, dict) else []
                if not isinstance(results, list):
                    results = []
                for label in results:
                    if not isinstance(label, dict):
                        continue
                    label_id = compact(str(label.get("id") or ""))
                    scan_key = label_id or compact(str(label.get("set_id") or ""))
                    if not scan_key or scan_key in scanned_ids:
                        continue
                    scanned_ids.add(scan_key)
                    counts["labels_scanned"] += 1
                    stats["labels_scanned_first_by_this_entry"] += 1

                    openfda = label.get("openfda") or {}
                    raw_names = openfda.get("substance_name") or openfda.get("generic_name") or []
                    raw_names = [compact(item) for item in raw_names if isinstance(item, str) and compact(item)]
                    normalized = sorted({normalized_substance(item) for item in raw_names if normalized_substance(item)})
                    if not normalized:
                        counts["labels_without_drug_identity"] += 1
                        continue
                    drug_id = slug("+".join(normalized))
                    if not drug_id:
                        counts["labels_without_drug_identity"] += 1
                        continue
                    # Added by Claude Code 2026-11-15: a product with four or more ingredients (prenatal
                    # vitamins and the like) is itself a supplement, not a drug to pair a supplement with.
                    if len(normalized) > MAX_DRUG_COMPONENTS or len(drug_id) > MAX_DRUG_ID_CHARS:
                        counts["labels_multi_ingredient_skipped"] += 1
                        continue

                    section_items = label.get("drug_interactions") or []
                    text = compact(" ".join(item for item in section_items if isinstance(item, str)))
                    if not text:
                        continue
                    set_id = compact(str(label.get("set_id") or label_id))
                    effective_time = compact(str(label.get("effective_time") or ""))
                    raw_joined = "; ".join(sorted(set(raw_names), key=lambda item: (item.lower(), item)))

                    skipped_entries: set[str] = set()
                    for entry in entries:
                        if entry["self_re"] and any(
                            pattern.search(name)
                            for pattern in entry["self_re"]
                            for name in normalized
                        ):
                            skipped_entries.add(entry["id"])
                            counts["self_skips"] += 1

                    # Abbreviation guards added by Claude Code 2026-11-15: without them "St. John's Wort"
                    # was cut after "St." and the sentence lost its subject.
                    sentences = re.split(
                        r"(?<!\bSt\.)(?<!\bST\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<!\bDr\.)(?<!\bNo\.)"
                        r"(?<=[.;])\s+(?=[A-Z0-9(])",
                        text,
                    )
                    for sentence in sentences:
                        if len(sentence) > args.max_sentence_chars:
                            counts["sentences_too_long"] += 1
                            continue
                        for entry in entries:
                            if entry["id"] in skipped_entries:
                                continue
                            match = entry["match_re"].search(sentence)
                            if match is None or any(pattern.search(sentence) for pattern in entry["exclude_re"]):
                                continue
                            key = (entry["id"], drug_id, sentence)
                            cited = {
                                "set_id": set_id,
                                "label_id": label_id,
                                "effective_time": effective_time,
                            }
                            item = aggregates.get(key)
                            if item is None:
                                aggregates[key] = {
                                    "entry": entry,
                                    "drug_id": drug_id,
                                    "sentence": sentence,
                                    "matched_text": match.group(0),
                                    "set_ids": {set_id},
                                    "raw_names": set(raw_names),
                                    "cited": cited,
                                }
                            else:
                                item["set_ids"].add(set_id)
                                item["raw_names"].update(raw_names)
                                old = item["cited"]
                                if (
                                    (effective_time, set_id, label_id)
                                    > (old["effective_time"], old["set_id"], old["label_id"])
                                ):
                                    item["cited"] = cited
                                    item["matched_text"] = match.group(0)

                if args.sleep_seconds:
                    time.sleep(args.sleep_seconds)
                skip += args.page_size
                if not results or total is None or skip >= total:
                    break

    per_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in aggregates.values():
        per_pair[(item["entry"]["id"], item["drug_id"])].append(item)

    selected: list[dict[str, Any]] = []
    # With cached pages the honest retrieval time is when the oldest page was downloaded, not now.
    retrieved_at = (
        datetime.fromtimestamp(min(CACHE_TIMES), timezone.utc).replace(microsecond=0).isoformat()
        if CACHE_TIMES else utc_now()
    )
    for pair_key in sorted(per_pair):
        # Labels repeat the same sentence with different spacing, bullets or quote marks. Keep one
        # verbatim copy (the most widely used) and count every label that carries any variant.
        merged: dict[str, dict[str, Any]] = {}
        for item in sorted(
            per_pair[pair_key],
            key=lambda item: (-len(item["set_ids"]), len(item["sentence"]), item["sentence"]),
        ):
            variant_key = near_duplicate_key(item["sentence"])
            kept = merged.get(variant_key)
            if kept is None:
                merged[variant_key] = item
            else:
                kept["set_ids"].update(item["set_ids"])
                kept["raw_names"].update(item["raw_names"])
                counts["near_duplicate_sentences_merged"] += 1
        items = sorted(
            merged.values(),
            key=lambda item: (-len(item["set_ids"]), len(item["sentence"]), item["sentence"]),
        )[:args.per_pair]
        selected.extend(items)

    rows: list[dict[str, Any]] = []
    for item in selected:
        entry = item["entry"]
        cited = item["cited"]
        sentence = item["sentence"]
        statement_id = hashlib.sha1(
            f'{entry["id"]}|{item["drug_id"]}|{sentence}'.encode("utf-8")
        ).hexdigest()[:16]
        rows.append({
            "statement_id": statement_id,
            "record_kind": "fda_label_statement",
            "review_status": "fda_approved_label_text_not_reviewed_by_supptracker",
            "supplement_id": entry["id"],
            "supplement_name": entry["name"],
            "supplement_kind": entry["kind"],
            "drug_id": item["drug_id"],
            "drug_names_raw": "; ".join(sorted(item["raw_names"], key=lambda value: (value.lower(), value))),
            "sentence": sentence,
            "matched_text": item["matched_text"],
            "section": "DRUG INTERACTIONS",
            "set_id": cited["set_id"],
            "label_id": cited["label_id"],
            "effective_time": cited["effective_time"],
            "label_count": len(item["set_ids"]),
            "source_url": label_source_url(cited["set_id"]),
            "retrieved_at": retrieved_at,
            "rights_status": "cc0_unless_otherwise_noted",
        })

    rows.sort(key=lambda row: (
        row["supplement_id"], row["drug_id"], -int(row["label_count"]), row["sentence"],
    ))
    write_csv(output_dir / "statements.csv", STATEMENT_FIELDS, rows)

    pair_rows: list[dict[str, Any]] = []
    # Fixed by Claude Code 2026-11-15: the generated comprehension referenced `row` and `key` out of scope (NameError).
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        grouped[(item["supplement_id"], item["drug_id"])].append(item)
    for (supplement_id, drug_id), item_rows in sorted(grouped.items(), key=lambda pair: pair[0]):
        pair_rows.append({
            "supplement_id": supplement_id,
            "drug_id": drug_id,
            "statements": len(item_rows),
            "labels": sum(int(row["label_count"]) for row in item_rows),
        })
    write_csv(output_dir / "pairs.csv", PAIR_FIELDS, pair_rows)

    for entry_id, stats in entry_stats.items():
        matching_rows = [row for row in rows if row["supplement_id"] == entry_id]
        stats["statements"] = len(matching_rows)
        stats["pairs"] = len({row["drug_id"] for row in matching_rows})

    counts["statements"] = len(rows)
    counts["distinct_pairs"] = len(pair_rows)
    counts["distinct_supplements"] = len({row["supplement_id"] for row in rows})
    counts["distinct_drugs"] = len({row["drug_id"] for row in rows})
    finished_at = utc_now()

    manifest = {
        "dataset_name": "SuppTracker openFDA supplement statements",
        "release_status": "fda_label_statements_not_clinically_reviewed",
        "source": {
            "api_url": API_URL,
            "license": "CC0-1.0 unless otherwise noted by openFDA",
            "license_url": LICENSE_URL,
            "meta_last_updated_seen": sorted(meta_updated),
        },
        "counts": counts,
        "per_entry": entry_stats,
        "pages_from_cache": len(CACHE_TIMES),
        "truncations": truncations,
        "failed_requests": failures,
        "arguments": {
            # File and folder names only: this manifest goes into a public repository.
            "terms": args.terms.name,
            "output_dir": args.output_dir.name,
            "max_drug_components": MAX_DRUG_COMPONENTS,
            "max_drug_id_chars": MAX_DRUG_ID_CHARS,
            "page_size": args.page_size,
            "max_pages": args.max_pages,
            "only": args.only,
            "sleep_seconds": args.sleep_seconds,
            "max_sentence_chars": args.max_sentence_chars,
            "per_pair": args.per_pair,
        },
        "dictionary_sha256": file_sha256(args.terms),
        "script_sha256": file_sha256(Path(__file__)),
        "started_at": started_at,
        "finished_at": finished_at,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--only")
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.35)
    parser.add_argument("--max-sentence-chars", type=int, default=700)
    parser.add_argument("--per-pair", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.page_size <= 1000:
        parser.error("--page-size must be from 1 through 1000")
    if args.max_pages < 0:
        parser.error("--max-pages must be zero or greater")
    if args.sleep_seconds < 0:
        parser.error("--sleep-seconds must be zero or greater")
    if args.max_sentence_chars < 1 or args.per_pair < 1:
        parser.error("--max-sentence-chars and --per-pair must be positive")
    try:
        counts = build(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
