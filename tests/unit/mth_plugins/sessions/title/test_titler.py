"""Unit tests for titler normalization, extraction, and bounds."""

from mth_plugins.sessions.title.titler import (
    SessionTitleState,
    clean_llm_title,
    extract_fallback_title,
    normalize_title_text,
    truncate_bytes,
)


def test_normalize_title_text() -> None:
    raw = "  Hello \x00\x05World!  \u200b\u200e\t This   is  a\ntest.  "
    normalized = normalize_title_text(raw)
    assert normalized == "Hello World! This is a test."


def test_truncate_bytes() -> None:
    text = "Short text"
    assert truncate_bytes(text, 50) == text

    # Multibyte truncate
    multibyte = "Hello 世界 world"
    truncated = truncate_bytes(multibyte, 10)
    assert len(truncated.encode("utf-8")) <= 10
    # Must decode cleanly without error
    truncated.encode("utf-8").decode("utf-8")


def test_extract_fallback_title() -> None:
    # Empty string fallback
    assert extract_fallback_title("") == "New Session"
    assert extract_fallback_title("   \t  ") == "New Session"

    # Max words limit
    long_prompt = "one two three four five six seven eight nine ten eleven twelve"
    fallback = extract_fallback_title(long_prompt, max_words=5)
    assert fallback == "one two three four five"

    # Max bytes limit
    assert len(extract_fallback_title(long_prompt, max_bytes=15).encode("utf-8")) <= 15


def test_clean_llm_title() -> None:
    assert clean_llm_title('  "Fixing the Build Bug."  ') == "Fixing the Build Bug"
    clean = clean_llm_title("### `Refactor Database Schema`:;")
    assert clean == "Refactor Database Schema"
    assert clean_llm_title("Ordinary Title") == "Ordinary Title"


def test_session_title_state() -> None:
    state = SessionTitleState()
    assert state.title is None
    assert state.source is None
    assert state.pinned is False
    assert state.restored is False
