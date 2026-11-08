"""Heuristic extraction and normalization routines for session titling."""

from __future__ import annotations

import re
from dataclasses import dataclass

TITLE_FALLBACK_MAX_WORDS = 8
TITLE_FALLBACK_MAX_BYTES = 96
TITLE_MAX_BYTES = 120


@dataclass
class SessionTitleState:
    """Tracks titling status and provenance for a session."""

    title: str | None = None
    source: str | None = None
    pinned: bool = False
    restored: bool = False


def normalize_title_text(text: str) -> str:
    """Removes control codes, zero-width chars, and collapses whitespaces."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    cleaned = re.sub(r"[\u200b-\u200f\u202a-\u202e]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def truncate_bytes(text: str, max_bytes: int) -> str:
    """Truncates UTF-8 encoded text cleanly without chopping multibyte sequences."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    while encoded and len(encoded) > max_bytes:
        encoded = encoded[:-1]
    return encoded.decode("utf-8", errors="ignore").rstrip()


def extract_fallback_title(
    first_user_text: str,
    max_words: int = TITLE_FALLBACK_MAX_WORDS,
    max_bytes: int = TITLE_FALLBACK_MAX_BYTES,
) -> str:
    """Extracts a concise fallback title from the initial user prompt."""
    normalized = normalize_title_text(first_user_text)
    words = normalized.split()
    if not words:
        return "New Session"
    limit = min(len(words), max_words)
    candidate = " ".join(words[:limit])
    return truncate_bytes(candidate, max_bytes)


def clean_llm_title(text: str, max_bytes: int = TITLE_MAX_BYTES) -> str:
    """Cleans quotation marks, punctuation, and length bounds from LLM titles."""
    normalized = normalize_title_text(text)
    # Strip leading/trailing quotation marks, markdown symbols, or punctuation
    cleaned = re.sub(r"^[\"#`*\s]+|[\"#`*.:;!?\s]+$", "", normalized)
    return truncate_bytes(cleaned, max_bytes)
