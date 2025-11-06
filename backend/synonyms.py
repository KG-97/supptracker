"""Utility helpers for parsing compound synonyms and aliases."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any, Iterator, List

__all__ = ["parse_synonyms"]


_WHITESPACE_PATTERN = re.compile(r"[\s\u200b]+")
_QUOTE_CHARS = "\"'`“”’"


def _strip_outer_quotes(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    while len(text) >= 2 and text[0] in _QUOTE_CHARS and text[-1] in _QUOTE_CHARS:
        text = text[1:-1].strip()
    return text


def _is_numeric_comma(text: str, index: int) -> bool:
    prev = index - 1
    while prev >= 0 and text[prev].isspace():
        prev -= 1
    nxt = index + 1
    length = len(text)
    while nxt < length and text[nxt].isspace():
        nxt += 1
    return prev >= 0 and nxt < length and text[prev].isdigit() and text[nxt].isdigit()


def _is_word_boundary(text: str, start: int, end: int) -> bool:
    prev = text[start - 1] if start > 0 else None
    nxt = text[end] if end < len(text) else None
    boundary_chars = {None, " ", "\t", "\n", "\r", ",", ";", "|", "/", "\\", "+", "&", "-", "(", ")"}
    return prev in boundary_chars and nxt in boundary_chars


def _tokenise_segment(segment: str) -> List[str]:
    cleaned = _WHITESPACE_PATTERN.sub(" ", segment).strip()
    if not cleaned:
        return []

    if "(" in cleaned and ")" in cleaned:
        open_idx = cleaned.find("(")
        close_idx = cleaned.rfind(")")
        if close_idx > open_idx:
            before = cleaned[:open_idx]
            inside = cleaned[open_idx + 1 : close_idx]
            after = cleaned[close_idx + 1 :]
            collected: List[str] = []
            if before.strip():
                collected.extend(_tokenise_segment(before))
            if inside.strip():
                collected.extend(_tokenise_segment(inside))
            if after.strip():
                collected.extend(_tokenise_segment(after))
            if collected:
                return collected

    tokens: List[str] = []
    buffer: List[str] = []
    i = 0
    length = len(cleaned)

    def _emit_buffer() -> None:
        if not buffer:
            return
        text = _strip_outer_quotes("".join(buffer))
        buffer.clear()
        if text:
            tokens.append(text)

    while i < length:
        chunk = cleaned[i:]
        lower = chunk.lower()
        if cleaned[i] == ",":
            if _is_numeric_comma(cleaned, i):
                buffer.append(cleaned[i])
            else:
                _emit_buffer()
            i += 1
            continue
        if cleaned[i] in {";", "|", "/", "\\", "+", "&"}:
            _emit_buffer()
            i += 1
            continue
        if lower.startswith("or") and _is_word_boundary(cleaned, i, i + 2):
            _emit_buffer()
            i += 2
            continue
        if lower.startswith("and") and _is_word_boundary(cleaned, i, i + 3):
            _emit_buffer()
            i += 3
            continue
        buffer.append(cleaned[i])
        i += 1

    _emit_buffer()

    return tokens or [_strip_outer_quotes(cleaned)]


def _flatten(value: Any) -> Iterator[str]:
    if value is None:
        return

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return

        if text.startswith(("[", "{")):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            else:
                if isinstance(parsed, (list, dict)):
                    yield from _flatten(parsed)
                    return
                if isinstance(parsed, (str, bytes, bytearray)):
                    yield from _flatten(parsed)
                    return
                if parsed is not None:
                    yield from _flatten(str(parsed))
                    return

        yield text
        return

    if isinstance(value, (bytes, bytearray)):
        try:
            decoded = value.decode("utf-8", errors="ignore")
        except Exception:
            decoded = ""
        if decoded:
            yield from _flatten(decoded)
        return

    if isinstance(value, dict):
        for item in value.values():
            yield from _flatten(item)
        return

    if isinstance(value, Iterable):
        for item in value:
            yield from _flatten(item)
        return

    text = str(value).strip()
    if text:
        yield text


def parse_synonyms(value: Any) -> List[str]:
    """Parse synonyms/aliases into a deterministic list of unique strings."""

    seen: set[str] = set()
    ordered: List[str] = []

    for raw in _flatten(value):
        for token in _tokenise_segment(raw):
            token_clean = token.strip()
            if not token_clean:
                continue
            # Case-fold to treat aliases with different casing as duplicates while
            # still preserving the first-seen capitalisation for display.
            dedupe_key = token_clean.casefold()
            if dedupe_key not in seen:
                seen.add(dedupe_key)
                ordered.append(token_clean)

    return ordered

