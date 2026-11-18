"""Row-aware splitting of FDA label text (scripts/label_text.py) and the corpus gate against merged rows."""

import csv
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from label_text import CROSSED_ROWS_RE, examples_statement, split_units  # noqa: E402

SJW = re.compile(r"St\.? John'?s Wort", re.IGNORECASE)

# Shape of the sertraline label table as openFDA flattens it (abridged).
TABLE = (
    "7.1 Clinically Significant Drug Interactions Table 4 Monoamine Oxidase Inhibitors (MAOIs) "
    "Clinical Impact: The concomitant use of SSRIs and MAOIs increases the risk of serotonin syndrome. "
    "Intervention: Sertraline is contraindicated in patients taking MAOIs. "
    "Examples: selegiline, tranylcypromine, linezolid, methylene blue "
    "Other Serotonergic Drugs Clinical Impact: The concomitant use of serotonergic drugs with sertraline "
    "increases the risk of serotonin syndrome. Intervention: Monitor patients for signs and symptoms of "
    "serotonin syndrome. Examples: other SSRIs, SNRIs, triptans, lithium, tryptophan, buspirone, and "
    "St. John's Wort Drugs that Interfere with Hemostasis (antiplatelet agents and anticoagulants) "
    "Clinical Impact: The concomitant use of an antiplatelet or anticoagulant with sertraline may potentiate "
    "the risk of bleeding. Intervention: Inform patients of the increased risk of bleeding. "
    "Examples: aspirin, clopidogrel, heparin, warfarin"
)


def _statements(text, pattern):
    found = []
    for unit in split_units(text):
        if unit.kind == "sentence":
            if pattern.search(unit.text):
                found.append(unit.text)
        else:
            for match in pattern.finditer(unit.text, unit.list_start):
                statement = examples_statement(unit, match.start(), match.end())
                if statement:
                    found.append(statement)
    return found


def test_examples_match_quotes_its_own_row_only():
    [statement] = _statements(TABLE, SJW)
    assert statement.startswith("Clinical Impact: The concomitant use of serotonergic drugs")
    assert statement.endswith("and St. John's Wort")
    assert "bleeding" not in statement and "Hemostasis" not in statement
    assert statement in TABLE
    assert not CROSSED_ROWS_RE.search(statement)


def test_middle_list_item_is_cut_after_the_item():
    [statement] = _statements(TABLE, re.compile("tryptophan", re.IGNORECASE))
    assert statement.endswith("lithium, tryptophan")
    assert "serotonin syndrome" in statement


def test_next_row_header_is_never_a_statement():
    text = TABLE.replace("Drugs that Interfere with Hemostasis (antiplatelet agents and anticoagulants)", "Ginkgo")
    text = text.replace("and St. John's Wort ", "and buspirone ")
    # "Ginkgo" now sits where the next row's header goes: not a list item, so no statement.
    assert _statements(text, re.compile("ginkgo", re.IGNORECASE)) == []


def test_header_text_is_dropped_from_sentence_blocks():
    texts = [unit.text for unit in split_units(TABLE) if unit.kind == "sentence"]
    assert "Drugs that Interfere with Hemostasis" not in " ".join(texts)
    assert all(not CROSSED_ROWS_RE.search(text) for text in texts)


def test_labels_without_spaces_are_still_boundaries():
    squeezed = TABLE.replace("Clinical Impact:", "ClinicalImpact:")
    [statement] = _statements(squeezed, SJW)
    assert statement.startswith("ClinicalImpact:") and "bleeding" not in statement


def test_plain_text_still_splits_into_sentences():
    # Same rule as before 2026-11-18: split after . or ; only before a capital, digit or "(".
    text = "Avoid St. John's Wort. It may reduce exposure; monitor levels. No other changes; Retest."
    assert [unit.text for unit in split_units(text)] == [
        "Avoid St. John's Wort.",
        "It may reduce exposure; monitor levels.",
        "No other changes;",
        "Retest.",
    ]


def test_corpus_has_no_statement_spanning_two_table_rows():
    path = PROJECT_ROOT / "data" / "openfda_supplement_statements" / "statements.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        crossed = [row["statement_id"] for row in csv.DictReader(handle) if CROSSED_ROWS_RE.search(row["sentence"])]
    assert crossed == []
