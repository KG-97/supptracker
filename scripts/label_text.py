"""Split openFDA drug-interaction text into statements without running one table row into the next.

Added by Claude Code 2026-11-18 after a live test found statements that glued the end of one table row
("Examples: ..., St. John's Wort") onto the next row's header and clinical impact ("Drugs that Interfere
with Hemostasis Clinical Impact: ... risk of bleeding"), so a serotonin-syndrome row read as a bleeding
warning. openFDA flattens label tables into plain text: each row is "<header> Clinical Impact: ...
Intervention: ... Examples: <list>", and the list has no closing full stop, so a plain sentence split ran on
into the next row.

Rules:
- "Clinical Impact:", "Intervention:" and "Examples:" are hard boundaries.
- Text after the last full stop of a block that is followed by a new row is that row's header; it is dropped.
- A name found in an Examples list becomes the row's own text: from its "Clinical Impact:" (when the row has
  one) through the list, cut just after the matched list item. A match that cannot be shown to be a list item
  (it may be the next row's header) gives no statement: fail closed.
- (2026-11-19, after Codex's review) A cell with no sentence end starts a new row, since a header could be
  hiding in it; a closing citation bracket "]" counts as a sentence end. In an Examples block followed by
  another row, a match at the very end of the block, or at/after a "lower-case word + Title-case word" join
  (where the next header most likely starts), gives no statement.
- (2026-11-19, after the cloud review) An Examples list that no later row follows stops at its first sentence
  end, subsection number ("7.2 Other Drugs") or likely header start, whichever comes first. The prose after
  it is split into ordinary sentences, and the list keeps the end-of-block and header guards, so a name in
  that prose is never quoted under the row's Clinical Impact.
- Known limit: a next-row header made of capitalised, comma-separated names after a capitalised last item
  ("Examples: Tramadol Antacids, Calcium, Iron <next row>") is not detected; no current label shows it.
Every statement returned is a verbatim substring of the input text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SENTENCE_SPLIT_RE = re.compile(
    r"(?:(?<!\bSt\.)(?<!\bST\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<!\bDr\.)(?<!\bNo\.)(?<=[.;])"
    r"|(?<=[.;][)\]]))\s+(?=[A-Z0-9(])"  # also after a closing bracket: "(see 5.1.) Next sentence"
)
# Row labels are capitalised table cells; prose such as "has a clinical impact:" is not one. Some labels
# lose their spaces ("ClinicalImpact:", even "WortClinical Impact:"), so no word boundary is required.
ROW_LABEL_RE = re.compile(
    r"(Clinical\s*Impact|CLINICAL\s*IMPACT|Interventions?|INTERVENTIONS?|Examples?|EXAMPLES?)\s*:"
)
# A sentence end, allowing closing brackets or quotes after it ("(see 5.1.)"); not "St.", "e.g.", "etc."
# or a botanical "L." (header text such as "(Antacids, H2 Blockers, etc.)" or "(Hypericum perforatum L.)").
_TERMINATOR_RE = re.compile(
    r"(?:(?<!\bSt)(?<!\bST)(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)(?<!\bDr)(?<!\bNo)(?<!\betc)(?<!\bL)[.!?][)\]\"'’”]*"
    r"|\])(?=\s|$)"  # a cell may end on its citation with no full stop: "... [see Clinical Pharmacology (12.3)]"
)
# Where the next row's header most likely starts inside an Examples block: a lower-case word followed by a
# Title-case word with no comma, semicolon, "and" or "or" between them ("tramadol Antacids, Calcium",
# "carbamazepine Moderate CYP3A4 Inducers"). Acronyms ("other SSRIs") and single capitals ("vitamin K") do
# not count. Added 2026-11-19 after Codex's review.
_HEADER_START_RE = re.compile(r"(?<![\w'’-])([a-z][\w'’-]*)\s+(?=[A-Z][a-z])")
# A label subsection number starting a heading: "7.2 Other Drugs". Added 2026-11-19 (cloud review).
_SECTION_START_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)+\s+(?=[A-Z])")
_ROW_ORDER = {"clinical impact": 0, "intervention": 1, "example": 2}
# A merged statement: an Examples or Intervention block followed by a later row's Clinical Impact.
CROSSED_ROWS_RE = re.compile(r"(Examples?|Interventions?)\s*:[\s\S]*Clinical\s*Impact\s*:", re.IGNORECASE)


@dataclass(frozen=True)
class Unit:
    """A piece of label text to match names in.

    kind "sentence": the whole text is a statement.
    kind "examples": text is the row context; names are matched only from ``list_start`` on, and the
    statement is cut after the matched item (see ``examples_statement``).
    """

    kind: str
    text: str
    list_start: int = 0
    followed_by_row: bool = False  # another table row follows, so the block ends with that row's header


def _label_name(match: re.Match[str]) -> str:
    name = re.sub(r"\s+", "", match.group(1).casefold()).rstrip("s")
    return "clinical impact" if name == "clinicalimpact" else name


def _drop_trailing_header(block: str) -> str:
    """Remove the next row's header from the end of a block (text after its last sentence end).

    A semicolon does not count as an end here: a header such as "St. John's Wort; Other Inducers" must
    not leave "St. John's Wort;" behind. A block with no sentence end is dropped whole (fail closed).
    """
    ends = list(_TERMINATOR_RE.finditer(block))
    if not ends:
        return ""
    return block[: ends[-1].end()].strip()


def _trailing_fragment(block: str) -> str:
    """Words after the block's last sentence end, if it has one: the signature of a next row's header."""
    ends = list(_TERMINATOR_RE.finditer(block))
    return block[ends[-1].end():].strip() if ends else ""


def _row_may_end_inside(block: str) -> bool:
    """True when a cell cannot be shown to end its row's text cleanly.

    Either words follow its last sentence end (a next row's header), or it has no sentence end at all, so a
    header could be hiding in it ("Clinical Impact: Serotonin syndrome Mineral Supplements Intervention: ...").
    """
    return not _TERMINATOR_RE.search(block) or bool(_trailing_fragment(block))


def _header_start(list_text: str) -> int:
    """Offset in an Examples list where the next row's header most likely starts, or len(list_text)."""
    for match in _HEADER_START_RE.finditer(list_text):
        if match.group(1).casefold() in ("and", "or"):
            continue
        if list_text.count("(", 0, match.start()) > list_text.count(")", 0, match.start()):
            continue  # inside brackets: "(e.g., rifampin, St. John's Wort)"
        return match.end()
    return len(list_text)


def _in_brackets(text: str, offset: int) -> bool:
    return text.count("(", 0, offset) > text.count(")", 0, offset)


def _last_list_end(block: str) -> int:
    """Offset in an Examples block that ends the text where its list stops (len(block) if it runs to the end).

    The list stops at the first of: a sentence end, a subsection number ("7.2 Other Drugs") or the likely
    start of a heading (see ``_header_start``), each outside brackets. Added 2026-11-19 after the cloud
    review: the whole remainder used to be one examples unit, so prose after the table was never split into
    sentences and a name in it was quoted under the last row's Clinical Impact.
    """
    label = ROW_LABEL_RE.match(block)
    list_from = label.end() if label else 0
    cuts = [len(block), list_from + _header_start(block[list_from:])]
    for pattern, edge in ((_TERMINATOR_RE, "end"), (_SECTION_START_RE, "start")):
        for match in pattern.finditer(block, list_from):
            if not _in_brackets(block, match.start()):
                cuts.append(match.end() if edge == "end" else match.start())
                break
    return min(cuts)


def runs_past_list(sentence: str) -> bool:
    """True when a statement goes on past the end of its last Examples list into further text
    ("Examples: ..., and isoniazid. • Carbonic anhydrase inhibitors ..."): built by the old sentence splitter,
    which ``split_units`` no longer produces. Added 2026-11-19."""
    labels = [item for item in ROW_LABEL_RE.finditer(sentence) if _label_name(item) == "example"]
    if not labels:
        return False
    block = sentence[labels[-1].start():]
    return bool(block[_last_list_end(block):].strip())


def split_units(text: str) -> list[Unit]:
    # A label inside brackets is prose ("(see Clinical Impact: Section 7)"), not a table cell.
    labels = [
        item for item in ROW_LABEL_RE.finditer(text)
        if text.count("(", 0, item.start()) <= text.count(")", 0, item.start())
    ]
    if not labels:
        return [Unit("sentence", piece) for piece in SENTENCE_SPLIT_RE.split(text) if piece.strip()]

    starts = [0] + [item.start() for item in labels]
    ends = [item.start() for item in labels] + [len(text)]
    kinds = [None] + [_label_name(item) for item in labels]
    # A label starts a new row when the order Clinical Impact < Intervention < Examples does not go up:
    # a row may lack any of the three, but its labels never repeat or go backwards. It also starts one
    # when the previous cell ends a sentence and then carries on: those words are the next row's header
    # ("...digoxin concentrations. Bleeding Risk Agents Intervention: ...").
    # A cell with no sentence end at all also starts a new row (fail closed): its row cannot be shown to go on.
    new_row = [False] + [
        position == 1
        or _ROW_ORDER[kinds[position]] <= _ROW_ORDER[kinds[position - 1]]
        or (position > 1 and _row_may_end_inside(text[starts[position - 1]:ends[position - 1]].strip()))
        for position in range(1, len(kinds))
    ]
    units: list[Unit] = []
    row_start = 0
    for position, (start, end, kind) in enumerate(zip(starts, ends, kinds)):
        if new_row[position]:
            row_start = start
        block = text[start:end].strip()
        next_starts_row = position + 1 < len(kinds) and new_row[position + 1]
        if kind == "example":
            list_end = end
            if position == len(kinds) - 1:  # no later row: the list may be followed by plain prose
                list_end = start + _last_list_end(text[start:end])
            prose = text[list_end:end].strip()
            context = text[row_start:list_end].strip()
            units.append(Unit(
                "examples", context, list_start=start - row_start,
                # Prose after the list is joined to it with no separator, just like a next row's header.
                followed_by_row=next_starts_row or bool(prose),
            ))
            units.extend(Unit("sentence", piece.strip()) for piece in SENTENCE_SPLIT_RE.split(prose) if piece.strip())
            continue
        if next_starts_row:
            block = _drop_trailing_header(block)
        for piece in SENTENCE_SPLIT_RE.split(block):
            if piece.strip():
                units.append(Unit("sentence", piece.strip()))
    return units


_ITEM_BEFORE_RE = re.compile(r"(?:^|[,;(]\s*|\b(?:and|or)\s+|:\s*)$", re.IGNORECASE)
_ITEM_AFTER_RE = re.compile(r"^(?:\s*[,;)]|\s+(?:and|or)\b)", re.IGNORECASE)
_LAST_ITEM_RE = re.compile(r"\b(?:and|or)\s+$", re.IGNORECASE)
_LIST_CONTINUES_RE = re.compile(r"^\s*[,;]")
_AND_OR_RE = re.compile(r"(?:,\s*|\s+)(?:and|or)\s+", re.IGNORECASE)


def _list_closers(before: str) -> list[int]:
    """End offsets of the top-level "and"/"or" words in ``before`` that close the list.

    ", and"/", or" always closes a list. A plain "and"/"or" closes it too unless more comma-separated items
    follow ("Thiazides and other diuretics, corticosteroids"). Anything after the item it introduces is the
    next row's header.
    """
    closers = []
    for item in _AND_OR_RE.finditer(before):
        if before.count("(", 0, item.start()) > before.count(")", 0, item.start()):
            continue  # inside brackets: "(tricyclic and serotonin uptake inhibitors)"
        if not item.group(0).startswith(",") and re.search(r"[,;]", before[item.end():]):
            continue  # a plain "and" with more items after it belongs to an item; ", and" always closes
        closers.append(item.end())
    return closers


def examples_statement(unit: Unit, match_start: int, match_end: int) -> str | None:
    """The row text cut after a list item matched at [match_start, match_end) of ``unit.text``.

    None when the match is not clearly a list item (it may be the next row's header).
    """
    if unit.kind != "examples" or match_start < unit.list_start:
        return None
    text = unit.text
    end = match_end
    while end < len(text) and (text[end].isalnum() or text[end] in "'’-"):
        end += 1  # finish the word
    before = text[unit.list_start:match_start]
    after = text[end:]
    if not _ITEM_BEFORE_RE.search(before):
        return None
    if unit.followed_by_row:
        # The block ends with the next row's header, which has no separator from the list. A match right at
        # the end of the block, or at/after where the header most likely starts, may be that header
        # ("Examples: tramadol Antacids, Calcium <next row> Clinical Impact: ..."): fail closed.
        if not after.strip():
            return None
        if match_start - unit.list_start >= _header_start(text[unit.list_start:]):
            return None
    # After "and X" the list is over; a later match sits in the next row's header.
    if any(end != len(before) for end in _list_closers(before)):
        return None
    depth = before.count("(") - before.count(")")
    if depth > 0:
        # Inside brackets: accept only when a comma or semicolon shows the list carries on after them
        # ("...) and Substrates" may be a header), and quote the whole bracket so it stays balanced.
        close = end
        while close < len(text) and depth > 0:
            depth += {"(": 1, ")": -1}.get(text[close], 0)
            close += 1
        if depth > 0 or not _LIST_CONTINUES_RE.match(text[close:]):
            return None
        return text[:close].strip()
    has_next_item = bool(_ITEM_AFTER_RE.match(after)) or not after.strip()
    if not (has_next_item or _LAST_ITEM_RE.search(before)):
        return None
    return text[:end].strip()
