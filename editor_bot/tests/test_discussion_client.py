"""Tests for discussion_client (resolve_discussion)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.discussion_client import resolve_discussion


@pytest.mark.asyncio
async def test_resolve_discussion_returns_none_when_api_returns_invalid_id_types() -> None:
    """When API returns discussion_chat_id as non-convertible type, return (None, None) without raising."""
    fake_resp = MagicMock()
    fake_resp.status = 200
    fake_resp.json = AsyncMock(
        return_value={
            "ok": True,
            "discussion_chat_id": "not_a_number",
            "discussion_message_id": 111,
        }
    )
    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=fake_resp)
    post_cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.post = MagicMock(return_value=post_cm)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("src.services.discussion_client.aiohttp.ClientSession", return_value=session_cm):
        cid, mid = await resolve_discussion("http://userbot:8081", "token", "-100123", 42)
    assert cid is None
    assert mid is None
