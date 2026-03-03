"""Text utilities for message splitting and Telegram HTML formatting."""

import html
import re

MESSAGE_LIMIT = 4096
"""Telegram Bot API limit for message text. We use a bit less for safety."""
CHUNK_LIMIT = 4000
# Max length for summary / edited_summary to avoid DoS and DB bloat
SUMMARY_MAX_LENGTH = 50_000

# Allowed Telegram HTML tags for our pipeline: b, i, blockquote only
_RE_STRIP_HTML = re.compile(r"<[^>]+>")


def strip_safe_html_to_plain(html_text: str | None) -> str:
    """Remove only <b>, <i>, <blockquote> tags for fallback plain send. Leaves text."""
    if not html_text:
        return ""
    return (
        (html_text or "")
        .replace("</blockquote>", "\n")
        .replace("<blockquote>", "")
        .replace("</b>", "")
        .replace("<b>", "")
        .replace("</i>", "")
        .replace("<i>", "")
    )


def summary_to_safe_html(text: str | None) -> str:
    """
    Convert summary to Telegram-safe HTML: **bold**, *italic*, "> quote" lines.
    Escapes raw HTML first; only produces <b>, <i>, <blockquote>. No nesting of b/i.
    Use with parse_mode=HTML. Safe for send_message.
    """
    if text is None or not text:
        return ""
    # Escape first so < > & are safe; then strip any raw tags (e.g. from broken input)
    s = html.escape(text)
    s = _RE_STRIP_HTML.sub("", s)
    # Blockquote: lines starting with "> " (after escape: "&gt; ")
    lines = s.split("\n")
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("&gt; "):
            quote_parts = [stripped[5:]]  # skip "&gt; "
            i += 1
            while i < len(lines) and lines[i].strip().startswith("&gt; "):
                quote_parts.append(lines[i].strip()[5:])
                i += 1
            out_lines.append("<blockquote>" + "\n".join(quote_parts) + "</blockquote>")
            continue
        out_lines.append(line)
        i += 1
    s = "\n".join(out_lines)
    # Bold: **...** -> <b>...</b>
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    # Italic: *...* -> <i>...</i> (single asterisks, no nesting with bold to avoid issues)
    s = re.sub(r"\*([^*]+?)\*", r"<i>\1</i>", s)
    return s


def summary_to_html(text: str | None) -> str:
    """
    Convert summary text with Markdown-style **bold** and *italic* to Telegram-safe HTML.
    Escapes HTML first to prevent injection. Use with parse_mode=HTML.
    (Legacy; for full safe pipeline use summary_to_safe_html.)
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


def split_html_safe(html_text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """
    Split HTML so that no chunk cuts inside a tag. Splits only after </b>, </i>,
    or </blockquote> (not at newlines, to avoid breaking blockquotes). Each chunk
    is valid HTML for Telegram parse_mode=HTML.
    """
    if not html_text or not html_text.strip():
        return []
    html_text = html_text.strip()
    if len(html_text) <= limit:
        return [html_text]
    chunks: list[str] = []
    rest = html_text
    # Safe break points: only after closing tags (splitting at \n would break <blockquote>)
    safe_ends = re.compile(r"(</b>|</i>|</blockquote>)")
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        piece = rest[: limit + 1]
        last_safe = -1
        for m in safe_ends.finditer(piece):
            last_safe = m.end()
        if last_safe <= 0:
            # No tag/newline in piece — fallback to last space
            last_safe = max(piece.rfind(" "), piece.rfind("\n"))
        if last_safe <= 0:
            last_safe = limit
        chunk = rest[:last_safe].strip()
        if chunk:
            chunks.append(chunk)
        rest = rest[last_safe:].strip()
    return chunks


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
