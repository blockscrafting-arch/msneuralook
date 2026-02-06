"""Tests for webhook sender."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.webhook_sender import send_to_n8n_webhook


@pytest.mark.asyncio
async def test_send_to_n8n_webhook_success() -> None:
    """On 200 response, returns True."""
    with patch("aiohttp.ClientSession") as session_cls:
        resp = AsyncMock()
        resp.status = 200
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)
        session = AsyncMock()
        session.post = MagicMock(return_value=resp)
        session_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await send_to_n8n_webhook(
            "http://test/webhook/xxx",
            post_text="Hello",
            pdf_path="/data/pdfs/1_2.pdf",
            message_id=2,
            channel_id="-100123",
            source_channel="-100123",
        )
        assert result is True


@pytest.mark.asyncio
async def test_send_to_n8n_webhook_failure() -> None:
    """On 500 response, returns False."""
    with patch("aiohttp.ClientSession") as session_cls:
        resp = AsyncMock()
        resp.status = 500
        resp.text = AsyncMock(return_value="Server Error")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)
        session = AsyncMock()
        session.post = MagicMock(return_value=resp)
        session_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await send_to_n8n_webhook(
            "http://test/webhook/xxx",
            post_text="",
            pdf_path="/data/x.pdf",
            message_id=1,
            channel_id="1",
            source_channel="src",
        )
        assert result is False
