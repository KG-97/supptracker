"""Read-only API for verbatim FDA supplement label statements."""

from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

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
        "directory": directory,
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
    item["label_count"] = int(row["label_count"])
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
    supplement: Optional[str] = Query(None, max_length=100),
    drug: Optional[str] = Query(None, max_length=100),
    q: Optional[str] = Query(None, max_length=100),
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
        supplement = supplement.strip().casefold()
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
def label_statements_pair(
    supplement: str = Query(..., max_length=100),
    drug: str = Query(..., max_length=100),
) -> Dict[str, Any]:
    """Return verbatim statements for one exact supplement and drug identifier."""

    if LABEL_STATEMENTS["status"] != "available":
        return {
            **_unavailable_response(),
            "total": 0,
            "items": [],
        }

    supplement = supplement.strip().casefold()
    drug = drug.strip().casefold()
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


# --- Free-text lookup -------------------------------------------------------------------------
# Lets the pair and stack checkers point at label text for the names a person typed. It resolves
# names only to decide which verbatim sentences to show. It never scores, ranks by risk or
# changes an assessment: every response carries assessment "not_assessed".

LOOKUP_MAX_NAMES = 20
LOOKUP_MAX_NAME_CHARS = 120
LOOKUP_MAX_PAIRS = 40
LOOKUP_MAX_DRUGS_PER_NAME = 10
LOOKUP_FOUND_MESSAGE = (
    "FDA label statements name these together. This is quoted label text, not an "
    "assessment by SuppTracker, and it does not cover every combination."
)
LOOKUP_NONE_MESSAGE = (
    "No FDA label statement in this collection names these together. This does not "
    "mean the combination is safe."
)

# Everyday spellings that label wording does not cover. Each is an exact, whole-name match
# for one supplement, so a partial or unknown name still resolves to nothing. They are used
# by the lookup only: the mining dictionary, and the hash recorded for it, are not touched.
LOOKUP_ALIASES: Dict[str, str] = {
    "grapefruit juice": "grapefruit",
    "coq10": "coenzyme-q10",
    "co q10": "coenzyme-q10",
    "coq 10": "coenzyme-q10",
    "co q 10": "coenzyme-q10",
    "k1": "vitamin-k",
    "k2": "vitamin-k",
    "d2": "vitamin-d",
    "d3": "vitamin-d",
    "cholecalciferol": "vitamin-d",
    "ergocalciferol": "vitamin-d",
    "b6": "vitamin-b6",
    "b12": "vitamin-b12",
    "b 12": "vitamin-b12",
    "b3": "niacin",
    "vitamin b3": "niacin",
    "5 htp": "tryptophan-5htp",
    "5htp": "tryptophan-5htp",
    "5 hydroxytryptophan": "tryptophan-5htp",
    "l tryptophan": "tryptophan-5htp",
    "saint john s wort": "st-johns-wort",
    "saint johns wort": "st-johns-wort",
    "retinol": "vitamin-a",
}

# These terms are supplements, ions, or excipients rather than sufficiently specific drug
# names. They must not expand to a drug product through a prefix or combination component.
GENERIC_DRUG_COMPONENTS = {
    "water",
    "sodium",
    "potassium",
    "calcium",
    "magnesium",
    "zinc",
    "iron",
    "chloride",
    "phosphate",
    "sulfate",
    "acetate",
}

_LOOKUP_INDEX: Dict[str, Any] = {"owner": None}


def _normalise_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()


def _load_term_patterns(directory: Path) -> Dict[str, Dict[str, Any]]:
    """Read the optional dictionary beside the corpus. Any problem means names match by id and name only."""

    try:
        source = json.loads((directory / "supplement_terms.json").read_text(encoding="utf-8"))
        patterns: Dict[str, Dict[str, Any]] = {}
        for entry in source["entries"]:
            patterns[str(entry["id"])] = {
                "search": {_normalise_name(str(term)) for term in entry.get("search", [])},
                "match": re.compile(str(entry["match"]), re.IGNORECASE),
                "exclude": [re.compile(str(item), re.IGNORECASE) for item in entry.get("exclude", [])],
            }
        return patterns
    except Exception:  # noqa: BLE001 - the dictionary is optional for lookups
        return {}


def _lookup_index() -> Dict[str, Any]:
    statements = LABEL_STATEMENTS["statements"]
    if _LOOKUP_INDEX["owner"] is statements:
        return _LOOKUP_INDEX

    patterns = _load_term_patterns(_dataset_directory(LABEL_STATEMENTS.get("directory")))
    supplements: Dict[str, Dict[str, Any]] = {}
    drugs: Dict[str, Dict[str, Any]] = {}
    by_pair: Dict[tuple[str, str], List[Dict[str, str]]] = {}
    for row in statements:
        supplement = supplements.setdefault(
            row["supplement_id"],
            {
                "supplement_id": row["supplement_id"],
                "supplement_name": row["supplement_name"],
                "is_group_term": row["supplement_kind"] in GROUP_KINDS,
                "statements": 0,
                "keys": {
                    _normalise_name(row["supplement_id"]),
                    _normalise_name(row["supplement_name"]),
                },
            },
        )
        supplement["statements"] += 1
        drug = drugs.setdefault(
            row["drug_id"],
            {
                "drug_id": row["drug_id"],
                "raw_names": set(),
                "statements": 0,
                "keys": set(),
                "combination_product": "+" in row["drug_id"],
                "single_ingredient_key": (
                    _normalise_name(row["drug_id"])
                    if "+" not in row["drug_id"]
                    else ""
                ),
            },
        )
        drug["statements"] += 1
        for raw_name in row["drug_names_raw"].split(";"):
            if raw_name.strip():
                drug["raw_names"].add(raw_name.strip())
                drug["keys"].add(_normalise_name(raw_name))
        for component in row["drug_id"].split("+"):
            component_key = _normalise_name(component)
            if component_key not in GENERIC_DRUG_COMPONENTS:
                drug["keys"].add(component_key)
        by_pair.setdefault((row["supplement_id"], row["drug_id"]), []).append(row)

    for supplement_id, supplement in supplements.items():
        supplement["keys"] |= patterns.get(supplement_id, {}).get("search", set())
        supplement["keys"].discard("")
    for alias, supplement_id in LOOKUP_ALIASES.items():
        if supplement_id in supplements:
            supplements[supplement_id]["keys"].add(alias)
    for drug in drugs.values():
        drug["keys"].discard("")

    _LOOKUP_INDEX.update(
        owner=statements, patterns=patterns, supplements=supplements, drugs=drugs, by_pair=by_pair
    )
    return _LOOKUP_INDEX


def search_label_names(query: str) -> List[Dict[str, Any]]:
    """Label-statement names for the search box, resolved exactly as the lookup endpoint resolves them.

    Claude Code 2026-11-18: a substring match here disagreed with the note under the search box (which
    uses the lookup), so "magnesi" hid "No compounds matched" while the note showed nothing.
    """
    key = recognised_name_key(query)
    if key is None:
        return []
    supplement_ids, drug_ids = key
    index = _lookup_index()
    matches: List[Dict[str, Any]] = [
        {
            "id": supplement_id,
            "name": index["supplements"][supplement_id]["supplement_name"],
            "kind": "supplement",
            "statements": index["supplements"][supplement_id]["statements"],
        }
        for supplement_id in supplement_ids
    ]
    for drug_id in sorted(drug_ids, key=lambda item: (-index["drugs"][item]["statements"], item)):
        drug = index["drugs"][drug_id]
        matches.append({
            "id": drug_id,
            "name": "; ".join(sorted(drug["raw_names"])) or drug_id,
            "kind": "drug",
            "statements": drug["statements"],
        })
    return matches[:10]


def supplement_suggestion_candidates() -> Dict[str, str]:
    """Map recognised supplement names and aliases to their display names."""
    if LABEL_STATEMENTS["status"] != "available":
        return {}
    index = _lookup_index()
    candidates: Dict[str, str] = {}
    for supplement in index["supplements"].values():
        for key in sorted(supplement["keys"]):
            candidates.setdefault(key, supplement["supplement_name"])
    return candidates


def _resolve_supplements(name: str, normalised: str, index: Dict[str, Any]) -> List[str]:
    matched = []
    for supplement_id, supplement in sorted(index["supplements"].items()):
        if normalised in supplement["keys"]:
            matched.append(supplement_id)
            continue
        pattern = index["patterns"].get(supplement_id)
        if pattern is None or any(item.search(name) for item in pattern["exclude"]):
            continue
        # The dictionary describes how labels word a supplement ("calcium supplements"), so a
        # bare name is also tried in that wording.
        if pattern["match"].fullmatch(name.strip()) or pattern["match"].fullmatch(
            f"{name.strip()} supplements"
        ):
            matched.append(supplement_id)
    return matched


def _resolve_drugs(normalised: str, index: Dict[str, Any]) -> List[str]:
    if normalised in GENERIC_DRUG_COMPONENTS:
        return []

    matched = []
    for drug_id, drug in sorted(index["drugs"].items()):
        for key in drug["keys"]:
            if key in GENERIC_DRUG_COMPONENTS:
                continue
            # Whole-word matching only: "warfarin" finds "warfarin sodium", "war" finds nothing.
            if key == normalised or key.startswith(normalised + " "):
                matched.append(drug_id)
                break
            if normalised.startswith(key + " ") and (
                len(key.split()) >= 2
                or (
                    not drug["combination_product"]
                    and key == drug["single_ingredient_key"]
                )
            ):
                matched.append(drug_id)
                break
    return matched


def recognised_name_key(name: str) -> Optional[tuple]:
    """Return the label lookup identities for a recognised name."""
    if LABEL_STATEMENTS["status"] != "available":
        return None
    name = " ".join(str(name).split())
    normalised = _normalise_name(name)
    if not normalised or len(name) > LOOKUP_MAX_NAME_CHARS:
        return None
    index = _lookup_index()
    if len(normalised) >= 3:
        supplements = _resolve_supplements(name, normalised, index)
        drugs = _resolve_drugs(normalised, index)
    else:
        supplements = sorted(
            supplement_id
            for supplement_id, supplement in index["supplements"].items()
            if normalised in supplement["keys"]
        )
        drugs = []
    if not supplements and not drugs:
        return None
    return (tuple(sorted(supplements)), tuple(sorted(drugs)))


# response_model=None: the function can return a JSONResponse, which FastAPI cannot turn into
# a response model (found by Antigravity's audit of this change).
@router.get("/api/label-statements/lookup", response_model=None)
def label_statements_lookup(
    names: List[str] = Query(default=[]),
) -> Dict[str, Any] | JSONResponse:
    """Find verbatim label statements that name any two of the given free-text names together."""

    cleaned = []
    for name in names:
        name = " ".join(str(name).split())
        if name and name.casefold() not in {item.casefold() for item in cleaned}:
            cleaned.append(name)
    if not cleaned or len(cleaned) > LOOKUP_MAX_NAMES:
        return JSONResponse(
            status_code=422,
            content={
                "status": "invalid",
                "assessment": "not_assessed",
                **_envelope(),
                "detail": f"Give between 1 and {LOOKUP_MAX_NAMES} names.",
            },
        )
    if any(len(name) > LOOKUP_MAX_NAME_CHARS for name in cleaned):
        return JSONResponse(
            status_code=422,
            content={
                "status": "invalid",
                "assessment": "not_assessed",
                **_envelope(),
                "detail": "A name is too long.",
            },
        )

    if LABEL_STATEMENTS["status"] != "available":
        return {
            **_unavailable_response(),
            "message": "FDA label statements are unavailable. Nothing has been assessed.",
            "names": [],
            "total_pairs": 0,
            "truncated": False,
            "pairs": [],
        }

    index = _lookup_index()
    resolved = []
    for name in cleaned:
        normalised = _normalise_name(name)
        if len(normalised) >= 3:
            supplement_ids = _resolve_supplements(name, normalised, index)
            drug_ids = _resolve_drugs(normalised, index)
        else:
            # Too short to match by wording. An exact key such as "K2" or "B6" is still
            # unambiguous; anything else resolves to nothing.
            supplement_ids = [
                supplement_id
                for supplement_id, supplement in sorted(index["supplements"].items())
                if normalised and normalised in supplement["keys"]
            ]
            drug_ids = []
        resolved.append((name, supplement_ids, drug_ids))

    groups: Dict[tuple[str, str], Dict[str, Any]] = {}
    for position, (supplement_input, supplement_ids, _) in enumerate(resolved):
        for other, (drug_input, _, drug_ids) in enumerate(resolved):
            if position == other:
                continue
            for supplement_id in supplement_ids:
                for drug_id in drug_ids:
                    rows = index["by_pair"].get((supplement_id, drug_id))
                    if not rows or (supplement_id, drug_id) in groups:
                        continue
                    supplement = index["supplements"][supplement_id]
                    groups[(supplement_id, drug_id)] = {
                        "supplement_input": supplement_input,
                        "drug_input": drug_input,
                        "supplement_id": supplement_id,
                        "supplement_name": supplement["supplement_name"],
                        "is_group_term": supplement["is_group_term"],
                        "drug_id": drug_id,
                        "drug_names_raw": "; ".join(
                            sorted(index["drugs"][drug_id]["raw_names"], key=str.casefold)
                        ),
                        "labels": sum(int(row["label_count"]) for row in rows),
                        "total": len(rows),
                        "items": [_statement_item(row) for row in rows],
                        "combination_product": index["drugs"][drug_id][
                            "combination_product"
                        ],
                    }

    # Ordered by how many labels carry the text, then by name. This is not a risk ranking.
    ordered = sorted(
        groups.values(),
        key=lambda group: (-group["labels"], group["supplement_id"], group["drug_id"]),
    )
    return {
        "status": "available",
        **_envelope(),
        "assessment": "not_assessed",
        "message": LOOKUP_FOUND_MESSAGE if ordered else LOOKUP_NONE_MESSAGE,
        "names": [
            {
                "input": name,
                "supplements": [
                    {
                        key: index["supplements"][supplement_id][key]
                        for key in ("supplement_id", "supplement_name", "is_group_term", "statements")
                    }
                    for supplement_id in supplement_ids
                ],
                "drug_total": len(drug_ids),
                "drugs": [
                    {
                        "drug_id": drug_id,
                        "drug_names_raw": "; ".join(
                            sorted(index["drugs"][drug_id]["raw_names"], key=str.casefold)
                        ),
                        "statements": index["drugs"][drug_id]["statements"],
                        "combination_product": index["drugs"][drug_id][
                            "combination_product"
                        ],
                    }
                    for drug_id in sorted(
                        drug_ids, key=lambda item: (-index["drugs"][item]["statements"], item)
                    )[:LOOKUP_MAX_DRUGS_PER_NAME]
                ],
            }
            for name, supplement_ids, drug_ids in resolved
        ],
        "total_pairs": len(ordered),
        "truncated": len(ordered) > LOOKUP_MAX_PAIRS,
        "pairs": ordered[:LOOKUP_MAX_PAIRS],
    }
