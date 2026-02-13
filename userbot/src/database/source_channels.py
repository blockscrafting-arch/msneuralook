"""Read active source channels and keywords from DB (same schema as editor_bot)."""

import asyncpg


async def get_keywords(pool: asyncpg.Pool) -> list[str]:
    """
    Return list of keyword (marker) words for post filtering.
    If empty or table missing (migration not applied), userbot does not filter by keywords.
    """
    try:
        rows = await pool.fetch(
            "SELECT word FROM keywords ORDER BY created_at"
        )
        return [r["word"].strip().lower() for r in rows if r["word"]]
    except asyncpg.UndefinedTableError:
        return []


async def get_active_channel_identifiers(pool: asyncpg.Pool) -> list[str]:
    """
    Return list of channel_identifier for active source channels.

    Returns:
        List of strings (e.g. "-1001234567890", "@channel").
    """
    rows = await pool.fetch(
        """
        SELECT channel_identifier
        FROM source_channels
        WHERE is_active = TRUE
        ORDER BY created_at
        """
    )
    return [r["channel_identifier"] for r in rows]
