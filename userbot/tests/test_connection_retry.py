"""Tests for DB connection pool with retry."""

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
