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


# Cases from Antigravity's review (18 Nov 2026).
ROW1 = (
    "Clinical Impact: Increases risk of serotonin syndrome. Intervention: Monitor patients. "
    "Examples: selegiline, tranylcypromine, and linezolid "
)


def test_name_inside_next_row_header_after_a_closed_list_is_rejected():
    for header in ("CYP3A4 Inducers (e.g., St. John's Wort)", "Strong Inducers and St. John's Wort"):
        text = ROW1 + header + " Clinical Impact: Decreased exposure."
        assert _statements(text, SJW) == [], header


def test_row_without_clinical_impact_starts_a_new_row():
    text = (
        "MAOIs Clinical Impact: Risk of serotonin syndrome. Intervention: Contraindicated. "
        "Bleeding Risk Agents Intervention: Monitor for bleeding. Examples: aspirin, St. John's Wort, warfarin"
    )
    [statement] = _statements(text, SJW)
    assert statement == "Intervention: Monitor for bleeding. Examples: aspirin, St. John's Wort"


def test_lower_case_prose_is_not_a_row_label():
    text = "Co-administration with St. John's Wort has a clinical impact: reduced exposure. Monitor levels."
    assert _statements(text, SJW) == ["Co-administration with St. John's Wort has a clinical impact: reduced exposure."]


def test_closing_bracket_ends_a_sentence_and_semicolon_header_is_dropped():
    text = (
        "Clinical Impact: Serotonin syndrome. Intervention: Avoid St. John's Wort (see Section 5.1.) "
        "Next Row Clinical Impact: Bleeding. Intervention: Monitor patients. "
        "St. John's Wort; Other Inducers Clinical Impact: Reduced exposure."
    )
    assert _statements(text, SJW) == ["Intervention: Avoid St. John's Wort (see Section 5.1.)"]


def test_bracketed_item_counts_only_when_the_list_continues():
    good = "Clinical Impact: Lower exposure. Examples: strong inducers (e.g., rifampin, St. John's Wort), and carbamazepine"
    [statement] = _statements(good, SJW)
    assert statement.endswith("St. John's Wort)")
    bad = "Clinical Impact: Lower exposure. Examples: rifampin, carbamazepine Inducers (e.g., St. John's Wort) Clinical Impact: X."
    assert _statements(bad, SJW) == []


def test_last_item_without_and_before_a_header_is_skipped():
    # Fail closed: "St. John's wort Digoxin and Phenytoin" cannot be split into item and header.
    text = "Clinical Impact: Lower exposure. Examples: rifampin, phenytoin, St. John's wort Digoxin and Phenytoin Clinical Impact: Narrow index."
    assert _statements(text, SJW) == []


# Cases from Antigravity's second review (18 Nov 2026).
def test_row_starting_at_intervention_after_a_clinical_impact_only_row():
    text = (
        "Digoxin Clinical Impact: Increases serum digoxin concentrations. Bleeding Risk Agents "
        "Intervention: Monitor for bleeding. Examples: aspirin, and St. John's Wort"
    )
    [statement] = _statements(text, SJW)
    assert statement == "Intervention: Monitor for bleeding. Examples: aspirin, and St. John's Wort"


def test_header_abbreviations_are_not_sentence_ends():
    etc = (
        "Clinical Impact: Serotonin syndrome. Intervention: Avoid St. John's Wort (see Section 5.1.) "
        "Gastric Acid Reducing Agents (Antacids, H2 Blockers, etc.) Clinical Impact: Decreased exposure."
    )
    assert _statements(etc, SJW) == ["Intervention: Avoid St. John's Wort (see Section 5.1.)"]
    botanical = (
        "Clinical Impact: Bleeding. Intervention: Monitor INR. "
        "St. John's Wort (Hypericum perforatum L.) Clinical Impact: Reduced exposure."
    )
    assert _statements(botanical, SJW) == []


def test_label_inside_brackets_is_prose():
    text = "St. John's Wort reduces drug levels (see Clinical Impact: Section 7). Monitor levels."
    assert _statements(text, SJW) == ["St. John's Wort reduces drug levels (see Clinical Impact: Section 7)."]


def test_more_headers_that_must_not_pass_as_list_items():
    second_and = ROW1 + "Strong Inducers, Moderate Inducers, and St. John's Wort Clinical Impact: Decreased exposure."
    no_oxford = (
        "Clinical Impact: Increases risk of serotonin syndrome. Intervention: Monitor patients. "
        "Examples: selegiline and tranylcypromine Strong Inducers and St. John's Wort Clinical Impact: X."
    )
    bracket_and = (
        "Clinical Impact: Lower exposure. Examples: rifampin, carbamazepine Inducers (e.g., St. John's Wort) "
        "and Substrates Clinical Impact: X."
    )
    for text in (second_and, no_oxford, bracket_and):
        assert _statements(text, SJW) == [], text


def test_and_inside_an_item_does_not_close_the_list():
    text = (
        "Clinical Impact: Loss of glycemic control. Examples: Thiazides and other diuretics, phenytoin, "
        "nicotinic acid, sympathomimetics and isoniazid"
    )
    [statement] = _statements(text, re.compile("nicotinic acid", re.IGNORECASE))
    assert statement.endswith("phenytoin, nicotinic acid")


# Cases from Codex's review (19 Nov 2026).
CALCIUM = re.compile(r"\bcalcium\b", re.IGNORECASE)


def test_comma_header_after_a_list_without_and_is_not_a_list_item():
    for header in ("Antacids, Calcium", "Antacids, Calcium, Iron", "Antacids, Calcium or Iron"):
        text = f"Clinical Impact: Serotonin syndrome. Examples: tramadol {header} Clinical Impact: Reduced absorption."
        assert _statements(text, CALCIUM) == [], header


def test_cell_without_a_sentence_end_starts_a_new_row():
    text = "Clinical Impact: Serotonin syndrome Mineral Supplements Intervention: Separate doses. Examples: calcium"
    assert _statements(text, CALCIUM) == ["Intervention: Separate doses. Examples: calcium"]


def test_citation_bracket_ends_a_cell_and_keeps_the_row_whole():
    text = (
        "Clinical Impact: Antacids raise absorption [see Clinical Pharmacology (12.3)] "
        "Intervention: Separate doses. Examples: calcium, magnesium Next Row Clinical Impact: Other."
    )
    [statement] = _statements(text, CALCIUM)
    assert statement.startswith("Clinical Impact: Antacids raise absorption") and statement.endswith("Examples: calcium")
    header_in_cell = "Clinical Impact: Lower exposure [see (12.3)] Calcium Supplements Intervention: Space doses."
    assert _statements(header_in_cell, CALCIUM) == []


def test_list_without_and_before_a_title_case_header_keeps_its_items():
    # The repaired lurasidone row: no "and" in the list, the next header starts at "Moderate".
    text = (
        "Clinical Impact: Strong inducers lower exposure. Intervention: Do not use together. "
        "Examples: Rifampin, avasimibe, St. John's wort, phenytoin, carbamazepine Moderate CYP3A4 Inducers "
        "Clinical Impact: Moderate inducers lower exposure."
    )
    [statement] = _statements(text, SJW)
    assert statement.endswith("Examples: Rifampin, avasimibe, St. John's wort")


def test_examples_matched_text_is_the_first_match_in_the_quote():
    # The builder records the first match in the final quote, which the validator re-derives.
    text = "Clinical Impact: Calcium reduces exposure. Examples: calcium and iron"
    quotes = _statements(text, CALCIUM)
    assert "Clinical Impact: Calcium reduces exposure. Examples: calcium" in quotes
    assert all(CALCIUM.search(quote).group(0) == "Calcium" for quote in quotes)


def test_corpus_has_no_statement_spanning_two_table_rows():
    path = PROJECT_ROOT / "data" / "openfda_supplement_statements" / "statements.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        crossed = [row["statement_id"] for row in csv.DictReader(handle) if CROSSED_ROWS_RE.search(row["sentence"])]
    assert crossed == []
