"""Tests for DB connection pool with retry."""

import asyncio

import pytest
from unittest.mock import AsyncMock, patch

from src.database.connection import create_pool_with_retry


@pytest.mark.asyncio
async def test_create_pool_with_retry_succeeds_on_first_attempt() -> None:
    """When create_pool succeeds immediately, returns pool and no retries."""
    pool = AsyncMock()
    with patch("src.database.connection.asyncpg.create_pool", new_callable=AsyncMock, return_value=pool):
        result = await create_pool_with_retry(
            "postgresql://u:p@localhost/db",
            max_attempts=3,
            delay_seconds=0.01,
        )
    assert result is pool


@pytest.mark.asyncio
async def test_create_pool_with_retry_retries_then_succeeds() -> None:
    """When create_pool fails twice then succeeds, returns pool after 3rd attempt."""
    pool = AsyncMock()
    call_count = 0

    async def create_pool_side_effect(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("connection refused")
        return pool

    with patch("src.database.connection.asyncpg.create_pool", new_callable=AsyncMock, side_effect=create_pool_side_effect), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await create_pool_with_retry(
            "postgresql://u:p@localhost/db",
            max_attempts=5,
            delay_seconds=1.0,
        )
    assert result is pool
    assert call_count == 3


@pytest.mark.asyncio
async def test_create_pool_with_retry_raises_after_max_attempts() -> None:
    """When create_pool always fails, raises after max_attempts."""
    with patch("src.database.connection.asyncpg.create_pool", new_callable=AsyncMock, side_effect=ConnectionError("refused")), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ConnectionError, match="refused"):
            await create_pool_with_retry(
                "postgresql://u:p@localhost/db",
                max_attempts=3,
                delay_seconds=0.01,
            )
