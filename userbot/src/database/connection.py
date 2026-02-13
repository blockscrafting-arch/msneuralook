"""Asyncpg connection pool for userbot."""

import asyncio
from typing import Optional

import asyncpg
import structlog

log = structlog.get_logger()


async def create_pool(database_url: str, min_size: int = 1, max_size: int = 4) -> asyncpg.Pool:
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
    log.info("userbot_db_pool_created", min_size=min_size, max_size=max_size)
    return pool


async def create_pool_with_retry(
    database_url: str,
    min_size: int = 1,
    max_size: int = 4,
    max_attempts: int = 10,
    delay_seconds: float = 3.0,
) -> asyncpg.Pool:
    """
    Create asyncpg connection pool with retries on startup (e.g. when Postgres is not ready yet).

    Args:
        database_url: PostgreSQL connection string.
        min_size: Minimum connections in pool.
        max_size: Maximum connections in pool.
        max_attempts: Number of connection attempts before giving up.
        delay_seconds: Delay between attempts in seconds.

    Returns:
        asyncpg.Pool instance.

    Raises:
        Last exception if all attempts fail.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            pool = await asyncpg.create_pool(
                database_url,
                min_size=min_size,
                max_size=max_size,
                command_timeout=30,
            )
            log.info(
                "userbot_db_pool_created",
                min_size=min_size,
                max_size=max_size,
                attempt=attempt,
            )
            return pool
        except (OSError, ConnectionError, asyncio.TimeoutError) as e:
            last_exc = e
            log.warning(
                "userbot_db_connection_retry",
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(e),
            )
        except asyncpg.PostgresError as e:
            last_exc = e
            log.warning(
                "userbot_db_connection_retry",
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(e),
            )
        if attempt < max_attempts:
            await asyncio.sleep(delay_seconds)
    if last_exc is not None:
        log.error("userbot_db_connection_failed", attempts=max_attempts, error=str(last_exc))
        raise last_exc
    raise RuntimeError("userbot_db_connection_failed")


async def close_pool(pool: Optional[asyncpg.Pool]) -> None:
    """Close pool if not None."""
    if pool:
        await pool.close()
        log.info("userbot_db_pool_closed")
