"""Tests for TG publisher (mocked)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.publisher import publish_to_channel, publish_to_all_channels


@pytest.mark.asyncio
async def test_publish_to_channel_sends_message_when_no_file() -> None:
    """When pdf_path is under storage but file missing, sends message only."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    with patch("os.path.isfile", return_value=False):
        await publish_to_channel(
            bot, "-100123", "Summary text", "/data/pdfs/missing.pdf", "/data/pdfs"
        )
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][1] == "Summary text"


@pytest.mark.asyncio
async def test_publish_to_channel_sends_message_when_pdf_path_empty() -> None:
    """When pdf_path is empty string (text-only post), sends message only."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    await publish_to_channel(bot, "-100123", "Summary text", "")
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][1] == "Summary text"
    bot.send_document.assert_not_called()
@pytest.mark.asyncio
async def test_publish_to_channel_sends_text_then_pdf_with_reply() -> None:
    """When PDF exists, sends caption chunk(s) then document as reply (or to discussion)."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    bot.get_chat = AsyncMock(return_value=MagicMock(spec=["linked_chat_id"], linked_chat_id=None))
    bot.send_document = AsyncMock(return_value=MagicMock())
    with patch("os.path.isfile", return_value=True), patch("asyncio.sleep", new_callable=AsyncMock):
        await publish_to_channel(
            bot, "-100123", "Summary text", "/data/pdfs/ok.pdf", "/data/pdfs"
        )
    assert bot.send_message.call_count >= 1
    bot.send_document.assert_called_once()
    call_kw = bot.send_document.call_args[1]
    assert call_kw.get("reply_to_message_id") == 42


@pytest.mark.asyncio
async def test_publish_to_channel_caption_sent_without_asterisks() -> None:
    """Caption has ** and * stripped before sending; no raw asterisks in message."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    await publish_to_channel(
        bot, "-100123", "**bold** and *italic* here", ""
    )
    bot.send_message.assert_called_once()
    sent_text = bot.send_message.call_args[0][1]
    assert "*" not in sent_text
    assert "bold" in sent_text and "italic" in sent_text


@pytest.mark.asyncio
async def test_publish_to_channel_pdf_in_discussion_when_resolver_ok() -> None:
    """When userbot resolver returns ok, PDF is sent to discussion_chat_id with reply_to_message_id=discussion_message_id."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    bot.send_document = AsyncMock(return_value=MagicMock())
    with patch("os.path.isfile", return_value=True), patch("asyncio.sleep", new_callable=AsyncMock), patch(
        "src.services.publisher.resolve_discussion",
        new_callable=AsyncMock,
        return_value=(-1009876543210, 111),
    ):
        await publish_to_channel(
            bot,
            "-100123",
            "Summary",
            "/data/pdfs/ok.pdf",
            "/data/pdfs",
            userbot_api_url="http://userbot:8081",
            userbot_api_token="secret",
        )
    bot.send_document.assert_called_once()
    call_kw = bot.send_document.call_args[1]
    assert call_kw.get("reply_to_message_id") == 111
    # chat_id is passed as first positional (send_document(chat_id, document, ...))
    assert bot.send_document.call_args[0][0] == -1009876543210


@pytest.mark.asyncio
async def test_publish_to_channel_pdf_fallback_to_channel_when_resolver_fails() -> None:
    """When resolver returns (None, None), PDF is sent to channel with reply_to_message_id=channel_message_id."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    bot.send_document = AsyncMock(return_value=MagicMock())
    with patch("os.path.isfile", return_value=True), patch("asyncio.sleep", new_callable=AsyncMock), patch(
        "src.services.publisher.resolve_discussion",
        new_callable=AsyncMock,
        return_value=(None, None),
    ):
        await publish_to_channel(
            bot,
            "-100123",
            "Summary",
            "/data/pdfs/ok.pdf",
            "/data/pdfs",
            userbot_api_url="http://userbot:8081",
            userbot_api_token="secret",
        )
    bot.send_document.assert_called_once()
    call_kw = bot.send_document.call_args[1]
    assert call_kw.get("reply_to_message_id") == 42
    assert bot.send_document.call_args[0][0] == "-100123"


@pytest.mark.asyncio
async def test_publish_to_channel_pdf_discussion_retry_then_success() -> None:
    """First send_document to discussion raises ConnectionError, second attempt succeeds; fallback not used."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    bot.send_document = AsyncMock(
        side_effect=[ConnectionError("Connection lost"), MagicMock()],
    )
    with patch("os.path.isfile", return_value=True), patch("asyncio.sleep", new_callable=AsyncMock), patch(
        "src.services.publisher.resolve_discussion",
        new_callable=AsyncMock,
        return_value=(-1009876543210, 111),
    ):
        await publish_to_channel(
            bot,
            "-100123",
            "Summary",
            "/data/pdfs/ok.pdf",
            "/data/pdfs",
            userbot_api_url="http://userbot:8081",
            userbot_api_token="secret",
        )
    assert bot.send_document.call_count == 2
    for call in bot.send_document.call_args_list:
        assert call[0][0] == -1009876543210


@pytest.mark.asyncio
async def test_publish_to_channel_pdf_discussion_all_retries_fail_then_fallback() -> None:
    """All 3 send_document attempts to discussion fail; fallback sends PDF to channel."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    bot.send_document = AsyncMock(
        side_effect=[
            ConnectionError("Broken pipe"),
            ConnectionError("Broken pipe"),
            ConnectionError("Broken pipe"),
            MagicMock(),
        ],
    )
    with patch("os.path.isfile", return_value=True), patch("asyncio.sleep", new_callable=AsyncMock), patch(
        "src.services.publisher.resolve_discussion",
        new_callable=AsyncMock,
        return_value=(-1009876543210, 111),
    ):
        await publish_to_channel(
            bot,
            "-100123",
            "Summary",
            "/data/pdfs/ok.pdf",
            "/data/pdfs",
            userbot_api_url="http://userbot:8081",
            userbot_api_token="secret",
        )
    assert bot.send_document.call_count == 4
    assert bot.send_document.call_args_list[0][0][0] == -1009876543210
    assert bot.send_document.call_args_list[1][0][0] == -1009876543210
    assert bot.send_document.call_args_list[2][0][0] == -1009876543210
    assert bot.send_document.call_args_list[3][0][0] == "-100123"


@pytest.mark.asyncio
async def test_publish_to_channel_pdf_to_channel_timeout_retry_succeeds() -> None:
    """When PDF goes to channel (no discussion), first send_document timeout, retry succeeds."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    bot.send_document = AsyncMock(
        side_effect=[
            Exception("HTTP Client says - Request timeout error"),
            MagicMock(),
        ],
    )
    with patch("os.path.isfile", return_value=True), patch("asyncio.sleep", new_callable=AsyncMock):
        await publish_to_channel(
            bot, "-100123", "Summary", "/data/pdfs/ok.pdf", "/data/pdfs"
        )
    assert bot.send_document.call_count == 2
    assert bot.send_document.call_args[0][0] == "-100123"


@pytest.mark.asyncio
async def test_publish_to_all_channels_serialized() -> None:
    """Two concurrent publish_to_all_channels run one after the other (lock)."""
    order: list[str] = []

    async def tracked_noop(*args, **kwargs):
        order.append("start")
        await asyncio.sleep(0.02)
        order.append("end")

    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    with patch("src.services.publisher.publish_to_channel", side_effect=tracked_noop):
        await asyncio.gather(
            publish_to_all_channels(bot, ["-1001"], "T1", ""),
            publish_to_all_channels(bot, ["-1002"], "T2", ""),
        )
    assert order == ["start", "end", "start", "end"]
