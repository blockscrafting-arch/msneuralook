"""Tests for post handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.pdf_downloader import get_pdf_document


def test_get_pdf_document_no_media() -> None:
    """If message has no media, returns None."""
    msg = MagicMock()
    msg.media = None
    assert get_pdf_document(msg) is None


def test_get_pdf_document_not_document() -> None:
    """If media is not a document, returns None."""
    msg = MagicMock()
    msg.media = MagicMock()
    msg.media.document = None
    assert get_pdf_document(msg) is None


def test_get_pdf_document_text_only_message() -> None:
    """Message with text but no media (text-only post) has no PDF."""
    msg = MagicMock()
    msg.media = None
    msg.text = "Только текст поста"
    assert get_pdf_document(msg) is None


@pytest.mark.asyncio
async def test_handler_skips_empty_post() -> None:
    """Post with no PDF and no text is skipped; webhook is not called."""
    from src.handlers import new_post

    handlers = []

    def capture_handler(*args, **kwargs):
        def deco(f):
            handlers.append(f)
            return f

        return deco

    client = MagicMock()
    client.on = MagicMock(side_effect=capture_handler)
    config = MagicMock()
    config.PDF_STORAGE_PATH = "/data/pdfs"
    config.N8N_WEBHOOK_URL = "http://n8n/webhook"
    config.get_source_channel_fallback = MagicMock(return_value="")
    pool = AsyncMock()
    new_post.register_new_post_handler(client, config, pool)

    event = MagicMock()
    event.message = MagicMock()
    event.message.id = 1
    event.message.text = ""
    event.message.media = None
    event.message.peer_id = MagicMock(channel_id=123)

    with (
        patch.object(new_post, "_get_monitored", new_callable=AsyncMock, return_value={"123"}),
        patch.object(new_post, "send_to_n8n_webhook", new_callable=AsyncMock) as mock_webhook,
    ):
        await handlers[0](event)
    mock_webhook.assert_not_called()


@pytest.mark.asyncio
async def test_handler_sends_webhook_for_text_only_post() -> None:
    """Post with text but no PDF sends webhook with pdf_path empty."""
    from src.handlers import new_post

    handlers = []

    def capture_handler(*args, **kwargs):
        def deco(f):
            handlers.append(f)
            return f

        return deco

    client = MagicMock()
    client.on = MagicMock(side_effect=capture_handler)
    config = MagicMock()
    config.PDF_STORAGE_PATH = "/data/pdfs"
    config.N8N_WEBHOOK_URL = "http://n8n/webhook"
    config.get_source_channel_fallback = MagicMock(return_value="")
    pool = AsyncMock()
    new_post.register_new_post_handler(client, config, pool)

    event = MagicMock()
    event.message = MagicMock()
    event.message.id = 2
    event.message.text = "Только текст"
    event.message.media = None
    event.message.peer_id = MagicMock(channel_id=123)

    with (
        patch.object(new_post, "_get_monitored", new_callable=AsyncMock, return_value={"123"}),
        patch.object(new_post, "send_to_n8n_webhook", new_callable=AsyncMock, return_value=True) as mock_webhook,
    ):
        await handlers[0](event)
    mock_webhook.assert_called_once()
    call_kw = mock_webhook.call_args[1]
    assert call_kw["pdf_path"] == ""
    assert call_kw["post_text"] == "Только текст"


@pytest.mark.asyncio
async def test_handler_sends_webhook_for_pdf_and_text_post() -> None:
    """Post with PDF and text sends webhook with pdf_path and post_text."""
    from src.handlers import new_post

    handlers = []

    def capture_handler(*args, **kwargs):
        def deco(f):
            handlers.append(f)
            return f

        return deco

    client = MagicMock()
    client.on = MagicMock(side_effect=capture_handler)
    config = MagicMock()
    config.PDF_STORAGE_PATH = "/data/pdfs"
    config.N8N_WEBHOOK_URL = "http://n8n/webhook"
    config.get_source_channel_fallback = MagicMock(return_value="")
    pool = AsyncMock()
    new_post.register_new_post_handler(client, config, pool)

    event = MagicMock()
    event.message = MagicMock()
    event.message.id = 3
    event.message.text = "Подпись к PDF"
    event.message.media = MagicMock()
    event.message.peer_id = MagicMock(channel_id=123)

    with (
        patch.object(new_post, "_get_monitored", new_callable=AsyncMock, return_value={"123"}),
        patch.object(new_post, "get_pdf_document", return_value=MagicMock()),
        patch.object(
            new_post,
            "download_pdf_to_storage",
            new_callable=AsyncMock,
            return_value="/data/pdfs/123_3.pdf",
        ),
        patch.object(new_post, "send_to_n8n_webhook", new_callable=AsyncMock, return_value=True) as mock_webhook,
    ):
        await handlers[0](event)
    mock_webhook.assert_called_once()
    call_kw = mock_webhook.call_args[1]
    assert call_kw["pdf_path"] == "/data/pdfs/123_3.pdf"
    assert call_kw["post_text"] == "Подпись к PDF"
