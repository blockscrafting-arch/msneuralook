"""Tests for internal API: POST /discussion/resolve."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.web.app import create_app


@pytest.mark.asyncio
async def test_discussion_resolve_wrong_token_returns_403() -> None:
    """When Authorization Bearer token is wrong, returns 403."""
    app = create_app(None, api_token="secret")
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/discussion/resolve",
            json={"channel_id": "-100123", "message_id": 1},
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status == 403
        data = await resp.json()
        assert data.get("ok") is False
        assert "Forbidden" in (data.get("error") or "")


@pytest.mark.asyncio
async def test_discussion_resolve_no_auth_when_token_configured_returns_403() -> None:
    """When API token is set and request has no Bearer, returns 403."""
    app = create_app(None, api_token="secret")
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/discussion/resolve",
            json={"channel_id": "-100123", "message_id": 1},
        )
        assert resp.status == 403


@pytest.mark.asyncio
async def test_discussion_resolve_invalid_json_returns_400() -> None:
    """When body is not valid JSON, returns 400."""
    app = create_app(MagicMock(), api_token="secret")  # client set so we reach JSON parsing
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/discussion/resolve",
            data="not json",
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data.get("ok") is False


@pytest.mark.asyncio
async def test_discussion_resolve_missing_channel_id_returns_400() -> None:
    """When channel_id or message_id is missing, returns 400."""
    app = create_app(MagicMock(), api_token="secret")  # client set so we reach validation
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/discussion/resolve",
            json={"message_id": 1},
            headers={"Authorization": "Bearer secret"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data.get("ok") is False
        assert "channel_id" in (data.get("error") or "")


@pytest.mark.asyncio
async def test_discussion_resolve_success_returns_ok_and_ids() -> None:
    """When resolve_discussion_message returns ids, response is 200 with ok true and discussion_chat_id, discussion_message_id."""
    app = create_app(MagicMock(), api_token="secret")
    with patch(
        "src.web.app.resolve_discussion_message",
        new_callable=AsyncMock,
        return_value=(-1009876543210, 111),
    ):
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/discussion/resolve",
                json={"channel_id": "-100123", "message_id": 42},
                headers={"Authorization": "Bearer secret"},
            )
            assert resp.status == 200
            data = await resp.json()
            assert data.get("ok") is True
            assert data.get("discussion_chat_id") == -1009876543210
            assert data.get("discussion_message_id") == 111
