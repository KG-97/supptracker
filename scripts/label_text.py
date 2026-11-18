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
Every statement returned is a verbatim substring of the input text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SENTENCE_SPLIT_RE = re.compile(
    r"(?<!\bSt\.)(?<!\bST\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<!\bDr\.)(?<!\bNo\.)"
    r"(?<=[.;])\s+(?=[A-Z0-9(])"
)
# Row labels are capitalised table cells; prose such as "has a clinical impact:" is not one. Some labels
# lose their spaces ("ClinicalImpact:", even "WortClinical Impact:"), so no word boundary is required.
ROW_LABEL_RE = re.compile(
    r"(Clinical\s*Impact|CLINICAL\s*IMPACT|Interventions?|INTERVENTIONS?|Examples?|EXAMPLES?)\s*:"
)
# A sentence end, allowing closing brackets or quotes after it ("(see 5.1.)"); not "St." or "e.g.".
_TERMINATOR_RE = re.compile(
    r"(?<!\bSt)(?<!\bST)(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)(?<!\bDr)(?<!\bNo)[.!?][)\]\"'’”]*(?=\s|$)"
)
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


def split_units(text: str) -> list[Unit]:
    labels = list(ROW_LABEL_RE.finditer(text))
    if not labels:
        return [Unit("sentence", piece) for piece in SENTENCE_SPLIT_RE.split(text) if piece.strip()]

    starts = [0] + [item.start() for item in labels]
    ends = [item.start() for item in labels] + [len(text)]
    kinds = [None] + [_label_name(item) for item in labels]
    # A label starts a new row when the order Clinical Impact < Intervention < Examples does not go up:
    # a row may lack any of the three, but its labels never repeat or go backwards.
    new_row = [False] + [
        position == 1 or _ROW_ORDER[kinds[position]] <= _ROW_ORDER[kinds[position - 1]]
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
            context = text[row_start:end].strip()
            units.append(Unit("examples", context, list_start=start - row_start))
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
_LIST_CONTINUES_RE = re.compile(r"^\s*(?:[,;]|(?:and|or)\b)", re.IGNORECASE)
# ", and " / ", or " closes a list: anything after the item it introduces is the next row's header.
_LIST_CLOSER_RE = re.compile(r",\s+(?:and|or)\s+", re.IGNORECASE)


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
    # After ", and X" the list is over; a later match sits in the next row's header.
    closers = list(_LIST_CLOSER_RE.finditer(before))
    if closers and closers[-1].end() != len(before):
        return None
    depth = before.count("(") - before.count(")")
    if depth > 0:
        # Inside brackets: accept only when the list visibly carries on after them, and quote the
        # whole bracket so the statement stays balanced.
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
