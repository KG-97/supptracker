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
# Some labels lose their spaces ("ClinicalImpact:"), so the gap inside the label is optional.
ROW_LABEL_RE = re.compile(r"\b(Clinical\s*Impact|Interventions?|Examples?)\s*:", re.IGNORECASE)
# A full stop, semicolon, ! or ? that ends a sentence (not "St." or "e.g.").
_TERMINATOR_RE = re.compile(
    r"(?<!\bSt)(?<!\bST)(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)(?<!\bDr)(?<!\bNo)[.;!?](?=\s|$)"
)
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
    """Remove the next row's header from the end of a block (text after its last sentence end)."""
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
    units: list[Unit] = []
    row_start: int | None = None  # where the current row's "Clinical Impact:" begins
    for position, (start, end, kind) in enumerate(zip(starts, ends, kinds)):
        block = text[start:end].strip()
        next_kind = kinds[position + 1] if position + 1 < len(kinds) else None
        if kind == "clinical impact":
            row_start = start
        if kind == "example":
            context_start = row_start if row_start is not None else start
            context = text[context_start:end].strip()
            units.append(Unit("examples", context, list_start=start - context_start))
            row_start = None
            continue
        if next_kind == "clinical impact":
            block = _drop_trailing_header(block)
            if kind != "clinical impact":
                row_start = None
        for piece in SENTENCE_SPLIT_RE.split(block):
            if piece.strip():
                units.append(Unit("sentence", piece.strip()))
    return units


_ITEM_BEFORE_RE = re.compile(r"(?:^|[,;(]\s*|\b(?:and|or)\s+|:\s*)$", re.IGNORECASE)
_ITEM_AFTER_RE = re.compile(r"^(?:\s*[,;)]|\s+(?:and|or)\b)", re.IGNORECASE)
_LAST_ITEM_RE = re.compile(r"\b(?:and|or)\s+$", re.IGNORECASE)


def examples_statement(unit: Unit, match_start: int, match_end: int) -> str | None:
    """The row text cut after a list item matched at [match_start, match_end) of ``unit.text``.

    None when the match is not clearly a list item (it may be the next row's header).
    """
    if unit.kind != "examples" or match_start < unit.list_start:
        return None
    end = match_end
    while end < len(unit.text) and (unit.text[end].isalnum() or unit.text[end] in "'’-"):
        end += 1  # finish the word ("St. John's Wort" matched as "St. John's W" never happens, but be safe)
    before = unit.text[unit.list_start:match_start]
    after = unit.text[end:]
    is_item_start = bool(_ITEM_BEFORE_RE.search(before))
    has_next_item = bool(_ITEM_AFTER_RE.match(after)) or not after.strip()
    is_last_item = bool(_LAST_ITEM_RE.search(before))
    if not is_item_start or not (has_next_item or is_last_item):
        return None
    return unit.text[:end].strip()
