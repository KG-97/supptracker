"""Document search integration powered by Gemini embeddings.

This module provides a small abstraction that loads textual documents from a
configured directory, chunks them into passages, and optionally generates
embeddings using the Gemini API.  When the Gemini client or API key is not
available the searcher transparently falls back to a lightweight keyword and
fuzzy-matching strategy so the endpoint keeps working in offline environments
and during unit tests.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import google.generativeai as genai
except Exception:  # pragma: no cover - handled gracefully
    genai = None  # type: ignore[assignment]


@dataclass(slots=True)
class DocumentChunk:
    """Represents a searchable chunk of text."""

    chunk_id: str
    title: str
    content: str
    source_path: str
    preview: str
    keywords: Tuple[str, ...]
    embedding: Optional[List[float]] = field(default=None)

    def to_result(self, score: float) -> dict:
        snippet = _build_snippet(self.content, preview=self.preview)
        return {
            "id": self.chunk_id,
            "title": self.title,
            "snippet": snippet,
            "score": round(float(score), 4),
            "source": self.source_path,
        }


class GeminiEmbedder:
    """Thin wrapper around the Gemini embedding API."""

    def __init__(self, api_key: Optional[str], model: str, task_type: str = "RETRIEVAL_DOCUMENT"):
        self.api_key = api_key
        self.model_name = model
        self.task_type = task_type
        self._model = None
        self.available = False

        if not api_key:
            logger.info("Gemini API key not provided; document embeddings disabled")
            return

        if genai is None:  # pragma: no cover - dependency missing in tests
            logger.warning("google-generativeai not installed; cannot use Gemini embeddings")
            return

        try:
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(model)
            self.available = True
        except Exception as exc:  # pragma: no cover - network/auth errors
            logger.warning("Failed to initialise Gemini embeddings: %s", exc)
            self._model = None
            self.available = False

    def embed_document(self, text: str) -> Optional[List[float]]:
        if not self.available or self._model is None:
            return None
        trimmed = text.strip()
        if not trimmed:
            return None
        try:
            payload = self._model.embed_content(
                content=trimmed,
                task_type=self.task_type,
            )
            return _extract_embedding(payload)
        except Exception as exc:  # pragma: no cover - network/auth errors
            logger.warning("Gemini document embedding failed: %s", exc)
            return None

    def embed_query(self, query: str) -> Optional[List[float]]:
        if not self.available or self._model is None:
            return None
        trimmed = query.strip()
        if not trimmed:
            return None
        try:
            payload = self._model.embed_content(
                content=trimmed,
                task_type="RETRIEVAL_QUERY",
            )
            return _extract_embedding(payload)
        except Exception as exc:  # pragma: no cover - network/auth errors
            logger.warning("Gemini query embedding failed: %s", exc)
            return None


class DocumentSearchService:
    """High level document search helper with embedding + keyword ranking."""

    def __init__(
        self,
        chunks: Sequence[DocumentChunk],
        *,
        embedder: Optional[GeminiEmbedder] = None,
        source_description: Optional[str] = None,
    ):
        self._chunks: List[DocumentChunk] = list(chunks)
        self._embedder = embedder if embedder and embedder.available else None
        self._source_description = source_description or "docs"
        self._using_embeddings = False

        if self._embedder and self._chunks:
            embedded_any = False
            for chunk in self._chunks:
                vector = self._embedder.embed_document(_truncate_for_embedding(chunk.content))
                if vector:
                    chunk.embedding = vector
                    embedded_any = True
            self._using_embeddings = embedded_any
            if not embedded_any:
                logger.info("Gemini embedder configured but no embeddings were generated; falling back to keyword ranking")
        else:
            if not self._chunks:
                logger.info("No documents available for search; returning empty index")

    @property
    def documents_indexed(self) -> int:
        return len(self._chunks)

    @property
    def uses_embeddings(self) -> bool:
        return self._using_embeddings

    @property
    def embedding_model(self) -> Optional[str]:
        if self._embedder and self._embedder.available:
            return self._embedder.model_name
        return None

    @property
    def source_description(self) -> str:
        return self._source_description

    def search(self, query: str, *, limit: int = 5) -> List[dict]:
        query = query.strip()
        if not query or not self._chunks:
            return []

        limit = max(1, min(limit, 25))

        results: List[Tuple[float, DocumentChunk]] = []
        if self._using_embeddings:
            query_vector = self._embedder.embed_query(query) if self._embedder else None
            if query_vector:
                for chunk in self._chunks:
                    if not chunk.embedding:
                        continue
                    score = _cosine_similarity(query_vector, chunk.embedding)
                    if math.isnan(score):
                        continue
                    results.append((score, chunk))
        if not results:
            # Fallback to keyword + fuzzy scoring
            query_tokens = _tokenise(query)
            query_text = " ".join(query_tokens)
            for chunk in self._chunks:
                score = _keyword_score(chunk, query_tokens, query_text)
                if score <= 0:
                    continue
                results.append((score, chunk))

        results.sort(key=lambda item: item[0], reverse=True)
        return [chunk.to_result(score) for score, chunk in results[:limit]]

    @classmethod
    def from_environment(cls) -> "DocumentSearchService":
        base_dir = Path(os.getenv("SUPPTRACKER_DOCS_DIR", "docs"))
        chunks: List[DocumentChunk] = []
        description = str(base_dir)
        if base_dir.exists():
            chunks = list(_load_directory(base_dir))
        else:
            logger.info("Document directory %s not found; search endpoint will return an empty result set", base_dir)
        embedder = GeminiEmbedder(
            api_key=os.getenv("GEMINI_API_KEY"),
            model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-pro-embeddings"),
        )
        return cls(chunks, embedder=embedder, source_description=description)

    @classmethod
    def from_texts(
        cls,
        items: Sequence[Tuple[str, str, Optional[str]]],
        *,
        embedder: Optional[GeminiEmbedder] = None,
        source_description: str = "inline",
    ) -> "DocumentSearchService":
        chunks = []
        for index, (identifier, content, title) in enumerate(items):
            chunk_id = f"{identifier}#chunk-{index}"
            keywords = tuple(_tokenise(content))
            preview = _make_preview(content)
            chunk = DocumentChunk(
                chunk_id=chunk_id,
                title=title or identifier,
                content=content,
                source_path=identifier,
                preview=preview,
                keywords=keywords,
            )
            chunks.append(chunk)
        return cls(chunks, embedder=embedder, source_description=source_description)


def _extract_embedding(payload: object) -> Optional[List[float]]:
    if payload is None:
        return None
    if isinstance(payload, dict):
        if "embedding" in payload:
            return _extract_embedding(payload.get("embedding"))
        if "values" in payload:
            raw = payload.get("values")
            if isinstance(raw, list):
                return [_ensure_float(v) for v in raw]
        if "embeddings" in payload:
            raw_embeddings = payload.get("embeddings")
            if isinstance(raw_embeddings, list) and raw_embeddings:
                return _extract_embedding(raw_embeddings[0])
        if "data" in payload:
            return _extract_embedding(payload.get("data"))
    if isinstance(payload, list):
        try:
            return [_ensure_float(v) for v in payload]
        except TypeError:
            flattened: List[float] = []
            for item in payload:
                values = _extract_embedding(item)
                if values:
                    flattened.extend(values)
            return flattened or None
    return None


def _ensure_float(value: object) -> float:
    try:
        return float(value)
    except Exception:  # pragma: no cover - defensive
        return 0.0


def _load_directory(base_dir: Path) -> Iterable[DocumentChunk]:
    for path in sorted(base_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt", ".json"}:
            continue
        relative = path.relative_to(base_dir)
        try:
            yield from _load_file(path, relative)
        except Exception as exc:  # pragma: no cover - defensive log
            logger.warning("Skipping document %s due to error: %s", path, exc)


def _load_file(path: Path, relative: Path) -> Iterable[DocumentChunk]:
    text: str
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            for index, entry in enumerate(payload):
                if not isinstance(entry, dict):
                    continue
                content = str(entry.get("content") or entry.get("text") or "").strip()
                if not content:
                    continue
                title = str(entry.get("title") or entry.get("heading") or relative.stem)
                chunk_id = f"{relative.as_posix()}#item-{index}"
                keywords = tuple(_tokenise(content))
                preview = _make_preview(content)
                yield DocumentChunk(
                    chunk_id=chunk_id,
                    title=title,
                    content=content,
                    source_path=relative.as_posix(),
                    preview=preview,
                    keywords=keywords,
                )
        return

    with path.open("r", encoding="utf-8") as handle:
        text = handle.read()
    if not text.strip():
        return

    title = _extract_title(text, fallback=relative.stem)
    for index, chunk_text in enumerate(_chunk_text(text)):
        chunk_id = f"{relative.as_posix()}#chunk-{index}"
        preview = _make_preview(chunk_text)
        keywords = tuple(_tokenise(chunk_text))
        yield DocumentChunk(
            chunk_id=chunk_id,
            title=title,
            content=chunk_text,
            source_path=relative.as_posix(),
            preview=preview,
            keywords=keywords,
        )


def _chunk_text(text: str, *, max_chars: int = 900, min_chunk_chars: int = 180) -> Iterable[str]:
    paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n", text) if segment.strip()]
    if not paragraphs:
        yield text.strip()
        return

    buffer: List[str] = []
    buffer_len = 0
    for paragraph in paragraphs:
        cleaned = re.sub(r"\s+", " ", paragraph).strip()
        if not cleaned:
            continue
        if buffer_len + len(cleaned) + 1 <= max_chars:
            buffer.append(cleaned)
            buffer_len += len(cleaned) + 1
            continue
        if buffer:
            chunk = " ".join(buffer).strip()
            if len(chunk) >= min_chunk_chars or len(paragraphs) == 1:
                yield chunk
            else:
                buffer.append(cleaned)
                buffer_len += len(cleaned) + 1
                continue
        buffer = [cleaned]
        buffer_len = len(cleaned)

    if buffer:
        chunk = " ".join(buffer).strip()
        if chunk:
            yield chunk


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("# ")
        return stripped
    return fallback


def _make_preview(content: str, length: int = 220) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    if len(compact) <= length:
        return compact
    return f"{compact[:length].rstrip()}…"


def _tokenise(text: str) -> Tuple[str, ...]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return tuple(tokens)


def _build_snippet(content: str, *, preview: str) -> str:
    return preview if preview else _make_preview(content)


def _truncate_for_embedding(content: str, limit: int = 3000) -> str:
    if len(content) <= limit:
        return content
    return content[:limit]


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        length = min(len(a), len(b))
        a = a[:length]
        b = b[:length]
    numerator = 0.0
    sum_a = 0.0
    sum_b = 0.0
    for x, y in zip(a, b):
        numerator += x * y
        sum_a += x * x
        sum_b += y * y
    if sum_a == 0 or sum_b == 0:
        return 0.0
    return numerator / math.sqrt(sum_a * sum_b)


def _keyword_score(chunk: DocumentChunk, tokens: Tuple[str, ...], query_text: str) -> float:
    if not tokens:
        return 0.0
    token_matches = 0
    keywords = set(chunk.keywords)
    for token in tokens:
        if token in keywords:
            token_matches += 1
    coverage = token_matches / max(len(tokens), 1)
    title_ratio = SequenceMatcher(None, query_text, chunk.title.lower()).ratio()
    preview_ratio = SequenceMatcher(None, query_text, chunk.preview.lower()).ratio()
    base = token_matches + coverage + (title_ratio * 0.6) + (preview_ratio * 0.4)
    return base


__all__ = [
    "DocumentSearchService",
    "GeminiEmbedder",
    "DocumentChunk",
]
