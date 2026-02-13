"""Tests for text utils."""

import pytest

from src.utils.text import split_text, strip_markdown_asterisks, summary_to_html


def test_split_text_empty() -> None:
    assert split_text("") == []
    assert split_text("   ") == []


def test_split_text_under_limit() -> None:
    short = "Hello world"
    assert split_text(short) == [short]
    assert split_text(short, limit=5) == ["Hello", "world"]


def test_split_text_over_limit_splits_at_space() -> None:
    text = "a" * 100 + " " + "b" * 100
    result = split_text(text, limit=150)
    assert len(result) == 2
    assert result[0] == "a" * 100
    assert result[1] == "b" * 100


def test_split_text_over_limit_splits_at_newline() -> None:
    line1 = "x" * 100
    line2 = "y" * 100
    result = split_text(line1 + "\n" + line2, limit=150)
    assert len(result) == 2
    assert result[0] == line1
    assert result[1] == line2


def test_split_text_many_chunks() -> None:
    parts = ["word"] * 50
    text = " ".join(parts)
    result = split_text(text, limit=30)
    assert len(result) >= 2
    assert sum(len(c) for c in result) >= len(text) - (len(result) - 1)


# --- strip_markdown_asterisks ---


def test_strip_markdown_asterisks_empty() -> None:
    assert strip_markdown_asterisks("") == ""
    assert strip_markdown_asterisks(None) == ""


def test_strip_markdown_asterisks_bold() -> None:
    assert strip_markdown_asterisks("**bold**") == "bold"


def test_strip_markdown_asterisks_italic() -> None:
    assert strip_markdown_asterisks("*italic*") == "italic"


def test_strip_markdown_asterisks_mixed() -> None:
    assert strip_markdown_asterisks("**bold** and *italic*") == "bold and italic"


def test_strip_markdown_asterisks_plain_unchanged() -> None:
    assert strip_markdown_asterisks("Plain text") == "Plain text"
    assert strip_markdown_asterisks("No asterisks here.") == "No asterisks here."


def test_strip_markdown_asterisks_order_double_first() -> None:
    """** is removed first so pair does not leave two *."""
    assert strip_markdown_asterisks("**x**") == "x"
    assert strip_markdown_asterisks("a*b*c") == "abc"


# --- summary_to_html ---


def test_summary_to_html_empty() -> None:
    assert summary_to_html("") == ""
    assert summary_to_html("   ") == "   "
    assert summary_to_html(None) == ""


def test_summary_to_html_bold() -> None:
    assert summary_to_html("**bold**") == "<b>bold</b>"
    assert summary_to_html("text **bold** end") == "text <b>bold</b> end"


def test_summary_to_html_italic() -> None:
    assert summary_to_html("*italic*") == "<i>italic</i>"
    assert summary_to_html("a *b* c") == "a <i>b</i> c"


def test_summary_to_html_bold_then_italic() -> None:
    """Bold is applied first, then italic on remaining single asterisks."""
    assert summary_to_html("**bold** and *italic*") == "<b>bold</b> and <i>italic</i>"


def test_summary_to_html_escapes_html() -> None:
    """HTML special chars are escaped to prevent injection."""
    assert summary_to_html("<script>") == "&lt;script&gt;"
    assert summary_to_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"
    assert summary_to_html('"quoted"') == "&quot;quoted&quot;"


def test_summary_to_html_plain_unchanged() -> None:
    """Text without markdown is unchanged; single unpaired * is left as-is."""
    assert summary_to_html("Plain text") == "Plain text"
    assert summary_to_html("One * here") == "One * here"


def test_summary_to_html_real_style_summary() -> None:
    """Real-style summary: multiple bold/italic, newlines, quotes. No raw ** in output."""
    sample = (
        "**Why X does not explain Y?**\n\n"
        "**Insight:** **macro is not a sum of agents.**\n"
        "Example: **3% CPI vs 1.5% GDP deflator**\n"
        "*Channel updates daily with research.*"
    )
    out = summary_to_html(sample)
    assert "<b>" in out and "</b>" in out
    assert "<i>" in out and "</i>" in out
    # No unescaped raw ** left (bold was converted)
    assert "**" not in out
    # No unescaped < or > from injection
    assert "<" in out  # only our <b>/<i>
    assert ">" in out
    # Tags are balanced (simple check: count)
    assert out.count("<b>") == out.count("</b>")
    assert out.count("<i>") == out.count("</i>")


def test_summary_to_html_then_split_valid_chunks() -> None:
    """Long HTML after summary_to_html splits at spaces; chunks are safe to send."""
    raw = "**bold** " + "word " * 900  # > 4000 chars to force split
    html_text = summary_to_html(raw)
    chunks = split_text(html_text)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 4000
        # No broken half-tag at chunk end (we split at space, so </b> can be at end)
        assert "<<" not in c and ">>" not in c


def test_split_text_prompt_over_4096_returns_multiple_chunks() -> None:
    """Prompt-like text over 4096 chars splits into multiple chunks (for full prompt display)."""
    long_prompt = "Промпт OpenAI (полностью):\n\n" + "x " * 2100  # > 4000 chars
    chunks = split_text(long_prompt)
    assert len(chunks) >= 2
    assert sum(len(c) for c in chunks) >= len(long_prompt.strip()) - (len(chunks) - 1) * 2
