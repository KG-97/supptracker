from __future__ import annotations

import csv
from pathlib import Path

from scripts.substance_identity import is_same_substance


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "data" / "openfda_candidates" / "label_candidates.csv"


def test_same_substance_rule_matches_real_corpus_positive_pairs():
    pairs = [
        ("ondansetron-hydrochloride", "ondansetron"),
        ("aripiprazole-oral", "aripiprazole"),
        (
            "dextrose-monohydrate-sodium-chloride-sodium-lactate-potassium-chloride-calcium-chloride",
            "dextrose",
        ),
        ("dorzolamide-hydrochloride-timolol-maleate", "timolol-maleate"),
        ("amoxicillin-and-clavulanate-potassium", "clavulanate-potassium"),
        ("butalbital-acetaminophen-and-caffeine", "caffeine"),
        ("ranibizumab-leyk", "ranibizumab"),
        ("metformin-er-500-mg", "metformin-hydrochloride"),
    ]
    assert all(is_same_substance(*pair) for pair in pairs)


def test_same_substance_rule_keeps_real_corpus_negative_pairs():
    pairs = [
        ("allopurinol", "cyclophosphamide"),
        ("heparin-sodium", "warfarin-sodium"),
        ("insulin-lispro", "clonidine"),
        ("mesalamine", "azathioprine"),
        ("levoleucovorin-calcium", "fluorouracil"),
        ("etodolac", "phenytoin"),
        ("diazepam", "cimetidine"),
        ("amphetamine-sulfate", "ethosuximide"),
    ]
    assert not any(is_same_substance(*pair) for pair in pairs)


def test_checked_in_candidate_corpus_has_no_same_substance_pair():
    with CANDIDATES.open("r", newline="", encoding="utf-8") as handle:
        candidates = csv.DictReader(handle)
        same_substance_rows = [
            row["candidate_id"]
            for row in candidates
            if is_same_substance(
                row["subject_compound_id"],
                row["mentioned_compound_id"],
            )
        ]
    assert same_substance_rows == []
