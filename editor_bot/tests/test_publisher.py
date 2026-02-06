"""Tests for TG publisher (mocked)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.publisher import publish_to_channel


@pytest.mark.asyncio
async def test_publish_to_channel_sends_message_when_no_file() -> None:
    """When pdf_path is missing, sends message only."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    with patch("os.path.isfile", return_value=False):
        await publish_to_channel(bot, "-100123", "Summary text", "/nonexistent.pdf")
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][1] == "Summary text"
