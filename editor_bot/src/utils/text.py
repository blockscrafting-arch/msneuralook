"""Text utilities for message splitting and Telegram HTML formatting."""

import html
import re

MESSAGE_LIMIT = 4096
"""Telegram Bot API limit for message text. We use a bit less for safety."""
CHUNK_LIMIT = 4000
# Max length for summary / edited_summary to avoid DoS and DB bloat
SUMMARY_MAX_LENGTH = 50_000


def summary_to_html(text: str | None) -> str:
    """
    Convert summary text with Markdown-style **bold** and *italic* to Telegram-safe HTML.
    Escapes HTML first to prevent injection. Use with parse_mode=HTML.
    """
    if text is None or not text:
        return ""
    s = html.escape(text)
    # Bold: **...** -> <b>...</b>
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    # Italic: *...* -> <i>...</i> (only single asterisks remain after bold)
    s = re.sub(r"\*([^*]+?)\*", r"<i>\1</i>", s)
    return s


def strip_markdown_asterisks(text: str | None) -> str:
    """
    Remove ** and * from text (no HTML conversion). Returns safe string for display.
    Order: ** first, then *, so a pair ** does not become two single *.
    """
    if text is None:
        return ""
    return (text or "").replace("**", "").replace("*", "")


def split_text(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """
    Split text into chunks not exceeding limit characters.
    Splits at nearest space or newline to avoid breaking words.
    Returns a single-item list if text fits in limit.
    """
    if not text:
        return []
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        piece = rest[: limit + 1]
        last_break = max(
            piece.rfind(" "),
            piece.rfind("\n"),
        )
        if last_break <= 0:
            last_break = limit
        chunk = rest[:last_break].strip()
        if chunk:
            chunks.append(chunk)
        rest = rest[last_break:].strip()
    return chunks
