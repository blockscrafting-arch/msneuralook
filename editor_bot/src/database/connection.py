"""Asyncpg connection pool."""

from typing import Optional

import asyncpg
import structlog

log = structlog.get_logger()


async def create_pool(database_url: str, min_size: int = 2, max_size: int = 10) -> asyncpg.Pool:
    """
    Create asyncpg connection pool.

    Args:
        database_url: PostgreSQL connection string.
        min_size: Minimum connections in pool.
        max_size: Maximum connections in pool.

    Returns:
        asyncpg.Pool instance.
    """
    pool = await asyncpg.create_pool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
    )
    log.info("db_pool_created", min_size=min_size, max_size=max_size)
    return pool


async def close_pool(pool: Optional[asyncpg.Pool]) -> None:
    """Close pool if not None."""
    if pool:
        await pool.close()
        log.info("db_pool_closed")
