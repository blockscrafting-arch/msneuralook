"""Tests for n8n webhook receiver."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web
from src.webhook.n8n_receiver import handle_incoming_post


@pytest.mark.asyncio
async def test_handle_incoming_post_missing_post_id() -> None:
    """When post_id is missing, returns 400."""
    request = MagicMock()
    request.json = AsyncMock(return_value={"summary": "x"})
    request.app = {}
    resp = await handle_incoming_post(request)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_handle_incoming_post_invalid_json() -> None:
    """When body is not JSON, returns 400."""
    request = MagicMock()
    request.json = AsyncMock(side_effect=ValueError("bad"))
    request.app = {}
    resp = await handle_incoming_post(request)
    assert resp.status == 400
