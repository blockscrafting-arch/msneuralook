"""CRUD for admin panel: source_channels, admins, editors, config (target_channel)."""

from typing import Optional

import asyncpg
import structlog

log = structlog.get_logger()


# --- source_channels ---


async def get_active_source_channels(pool: asyncpg.Pool) -> list[dict]:
    """Return list of active source channels (channel_identifier, display_name, id)."""
    rows = await pool.fetch(
        """
        SELECT id, channel_identifier, display_name
        FROM source_channels WHERE is_active = TRUE
        ORDER BY created_at
        """
    )
    return [dict(r) for r in rows]


async def get_all_source_channels(pool: asyncpg.Pool) -> list[dict]:
    """Return all source channels for admin list."""
    rows = await pool.fetch(
        """
        SELECT id, channel_identifier, display_name, is_active, created_at
        FROM source_channels ORDER BY created_at
        """
    )
    return [dict(r) for r in rows]


async def add_source_channel(
    pool: asyncpg.Pool,
    channel_identifier: str,
    added_by: Optional[int] = None,
    display_name: str = "",
) -> Optional[int]:
    """Insert source channel. Returns id or None on unique violation."""
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO source_channels (channel_identifier, display_name, added_by)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            channel_identifier.strip(),
            (display_name or "").strip(),
            added_by,
        )
        return row["id"] if row else None
    except asyncpg.UniqueViolationError:
        return None


async def remove_source_channel(pool: asyncpg.Pool, channel_id: int) -> bool:
    """Delete source channel by id. Returns True if deleted."""
    result = await pool.execute(
        "DELETE FROM source_channels WHERE id = $1",
        channel_id,
    )
    return result == "DELETE 1"


async def set_source_channel_active(
    pool: asyncpg.Pool, channel_id: int, is_active: bool
) -> bool:
    """Set is_active for a source channel."""
    result = await pool.execute(
        "UPDATE source_channels SET is_active = $1 WHERE id = $2",
        is_active,
        channel_id,
    )
    return result == "UPDATE 1"


# --- admins ---


async def get_admin_user_ids(pool: asyncpg.Pool) -> set[int]:
    """Return set of user_id that are admins."""
    rows = await pool.fetch("SELECT user_id FROM admins")
    return {r["user_id"] for r in rows}


async def get_admins_list(pool: asyncpg.Pool) -> list[dict]:
    """Return list of admins (user_id, username) for display."""
    rows = await pool.fetch(
        "SELECT user_id, username FROM admins ORDER BY created_at"
    )
    return [dict(r) for r in rows]


async def add_admin(
    pool: asyncpg.Pool,
    user_id: int,
    username: str = "",
    added_by: Optional[int] = None,
) -> bool:
    """Add admin. Returns True if inserted, False if already exists."""
    row = await pool.fetchrow(
        """
        INSERT INTO admins (user_id, username, added_by)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO NOTHING
        RETURNING user_id
        """,
        user_id,
        (username or "").strip(),
        added_by,
    )
    return row is not None


async def remove_admin(pool: asyncpg.Pool, user_id: int) -> bool:
    """Remove admin by user_id. Returns True if deleted."""
    result = await pool.execute("DELETE FROM admins WHERE user_id = $1", user_id)
    return result == "DELETE 1"


async def is_admin(pool: asyncpg.Pool, user_id: int) -> bool:
    """Check if user_id is in admins table."""
    row = await pool.fetchrow(
        "SELECT 1 FROM admins WHERE user_id = $1", user_id
    )
    return row is not None


# --- editors ---


async def get_editor_user_ids(pool: asyncpg.Pool) -> set[int]:
    """Return set of user_id that are editors."""
    rows = await pool.fetch("SELECT user_id FROM editors")
    return {r["user_id"] for r in rows}


async def get_editors_list(pool: asyncpg.Pool) -> list[dict]:
    """Return list of editors (user_id, username) for display."""
    rows = await pool.fetch(
        "SELECT user_id, username FROM editors ORDER BY created_at"
    )
    return [dict(r) for r in rows]


async def add_editor(
    pool: asyncpg.Pool,
    user_id: int,
    username: str = "",
    added_by: Optional[int] = None,
) -> bool:
    """Add editor. Returns True if inserted, False if already exists."""
    row = await pool.fetchrow(
        """
        INSERT INTO editors (user_id, username, added_by)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO NOTHING
        RETURNING user_id
        """,
        user_id,
        (username or "").strip(),
        added_by,
    )
    return row is not None


async def remove_editor(pool: asyncpg.Pool, user_id: int) -> bool:
    """Remove editor by user_id. Returns True if deleted."""
    result = await pool.execute("DELETE FROM editors WHERE user_id = $1", user_id)
    return result == "DELETE 1"


async def is_editor(pool: asyncpg.Pool, user_id: int) -> bool:
    """Check if user_id is in editors table."""
    row = await pool.fetchrow(
        "SELECT 1 FROM editors WHERE user_id = $1", user_id
    )
    return row is not None


# --- keyword_groups (group -> target_channel for routing) ---


async def get_all_keyword_groups(pool: asyncpg.Pool) -> list[dict]:
    """Return all keyword groups with channel_identifier (join target_channels)."""
    try:
        rows = await pool.fetch(
            """
            SELECT kg.id, kg.name, kg.target_channel_id, kg.created_at,
                   tc.channel_identifier, tc.display_name AS channel_display_name
            FROM keyword_groups kg
            JOIN target_channels tc ON kg.target_channel_id = tc.id
            ORDER BY kg.created_at
            """
        )
        return [dict(r) for r in rows]
    except asyncpg.UndefinedTableError:
        return []


async def get_keyword_group_by_id(pool: asyncpg.Pool, group_id: int) -> Optional[dict]:
    """Return one keyword group by id or None."""
    try:
        row = await pool.fetchrow(
            """
            SELECT kg.id, kg.name, kg.target_channel_id, kg.created_at,
                   tc.channel_identifier, tc.display_name AS channel_display_name
            FROM keyword_groups kg
            JOIN target_channels tc ON kg.target_channel_id = tc.id
            WHERE kg.id = $1
            """,
            group_id,
        )
        return dict(row) if row else None
    except asyncpg.UndefinedTableError:
        return None


async def add_keyword_group(
    pool: asyncpg.Pool,
    name: str,
    target_channel_id: int,
    added_by: Optional[int] = None,
) -> Optional[int]:
    """Insert keyword group. Returns id or None on FK violation."""
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO keyword_groups (name, target_channel_id, added_by)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            (name or "").strip(),
            target_channel_id,
            added_by,
        )
        return row["id"] if row else None
    except (asyncpg.UndefinedTableError, asyncpg.ForeignKeyViolationError):
        return None


async def update_keyword_group(
    pool: asyncpg.Pool,
    group_id: int,
    name: Optional[str] = None,
    target_channel_id: Optional[int] = None,
) -> bool:
    """Update keyword group name and/or target_channel_id. Returns True if updated."""
    try:
        if name is not None and target_channel_id is not None:
            result = await pool.execute(
                """
                UPDATE keyword_groups SET name = $1, target_channel_id = $2
                WHERE id = $3
                """,
                name.strip(),
                target_channel_id,
                group_id,
            )
        elif name is not None:
            result = await pool.execute(
                "UPDATE keyword_groups SET name = $1 WHERE id = $2",
                name.strip(),
                group_id,
            )
        elif target_channel_id is not None:
            result = await pool.execute(
                "UPDATE keyword_groups SET target_channel_id = $1 WHERE id = $2",
                target_channel_id,
                group_id,
            )
        else:
            return False
        return result == "UPDATE 1"
    except (asyncpg.UndefinedTableError, asyncpg.ForeignKeyViolationError):
        return False


async def remove_keyword_group(pool: asyncpg.Pool, group_id: int) -> bool:
    """Delete keyword group. Markers with this group_id get group_id=NULL (ON DELETE SET NULL)."""
    try:
        result = await pool.execute(
            "DELETE FROM keyword_groups WHERE id = $1",
            group_id,
        )
        return result == "DELETE 1"
    except asyncpg.UndefinedTableError:
        return False


async def get_target_channel_ids_by_text(pool: asyncpg.Pool, text: str) -> list[str]:
    """
    Return list of channel_identifier for groups that have at least one marker present in text.
    Used for routing: post text is matched against group markers; only those channels are returned.
    If no groups or no matches, returns [] (caller should use fallback: all active channels).
    """
    if not text or not text.strip():
        return []
    try:
        rows = await pool.fetch(
            """
            SELECT kg.id, tc.channel_identifier, k.word
            FROM keyword_groups kg
            JOIN target_channels tc ON kg.target_channel_id = tc.id AND tc.is_active = TRUE
            JOIN keywords k ON k.group_id = kg.id
            ORDER BY kg.id
            """
        )
    except asyncpg.UndefinedTableError:
        return []
    text_lower = text.lower()
    seen_channels: set[str] = set()
    matched_channels: list[str] = []
    for r in rows:
        ch = r["channel_identifier"]
        word = (r["word"] or "").strip().lower()
        if word and word in text_lower and ch and ch not in seen_channels:
            seen_channels.add(ch)
            matched_channels.append(ch)
    return matched_channels


async def get_channel_ids_for_publish(
    pool: asyncpg.Pool,
    text: str,
    fallback_channel_from_config: Optional[str] = None,
) -> list[str]:
    """
    Return list of channel_identifier to publish to. If groups match text, return those channels;
    otherwise return all active target channels (or single fallback from config).
    """
    channel_ids = await get_target_channel_ids_by_text(pool, text or "")
    if channel_ids:
        return channel_ids
    channels_list = await get_active_target_channels(pool)
    channel_ids = [ch["channel_identifier"] for ch in channels_list if ch.get("channel_identifier")]
    if channel_ids:
        return channel_ids
    if fallback_channel_from_config and fallback_channel_from_config.strip():
        return [fallback_channel_from_config.strip()]
    return []


# --- keywords (markers for userbot filtering) ---


async def get_all_keywords(pool: asyncpg.Pool) -> list[dict]:
    """Return all keywords for admin list. Includes group_id and group_name if migration 008 applied."""
    try:
        rows = await pool.fetch(
            """
            SELECT k.id, k.word, k.created_at, k.group_id, kg.name AS group_name
            FROM keywords k
            LEFT JOIN keyword_groups kg ON k.group_id = kg.id
            ORDER BY k.created_at
            """
        )
        return [dict(r) for r in rows]
    except asyncpg.UndefinedColumnError:
        rows = await pool.fetch(
            "SELECT id, word, created_at FROM keywords ORDER BY created_at"
        )
        return [dict(r) for r in rows]
    except asyncpg.UndefinedTableError:
        return []


async def add_keyword(
    pool: asyncpg.Pool,
    word: str,
    added_by: Optional[int] = None,
    group_id: Optional[int] = None,
) -> Optional[int]:
    """Insert keyword. Returns id or None on unique violation or invalid group_id (FK). group_id optional (migration 008)."""
    word_clean = (word or "").strip().lower()
    if not word_clean:
        return None
    try:
        if group_id is not None:
            row = await pool.fetchrow(
                """
                INSERT INTO keywords (word, added_by, group_id)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                word_clean,
                added_by,
                group_id,
            )
        else:
            row = await pool.fetchrow(
                """
                INSERT INTO keywords (word, added_by)
                VALUES ($1, $2)
                RETURNING id
                """,
                word_clean,
                added_by,
            )
        return row["id"] if row else None
    except asyncpg.UniqueViolationError:
        return None
    except asyncpg.ForeignKeyViolationError:
        return None
    except asyncpg.UndefinedColumnError:
        row = await pool.fetchrow(
            """
            INSERT INTO keywords (word, added_by)
            VALUES ($1, $2)
            RETURNING id
            """,
            word_clean,
            added_by,
        )
        return row["id"] if row else None


async def remove_keyword(pool: asyncpg.Pool, keyword_id: int) -> bool:
    """Delete keyword by id. Returns True if deleted."""
    result = await pool.execute("DELETE FROM keywords WHERE id = $1", keyword_id)
    return result == "DELETE 1"


async def get_keywords_by_group_id(pool: asyncpg.Pool, group_id: int) -> list[dict]:
    """Return keywords that belong to the given group (for group detail screen)."""
    try:
        rows = await pool.fetch(
            "SELECT id, word, created_at FROM keywords WHERE group_id = $1 ORDER BY created_at",
            group_id,
        )
        return [dict(r) for r in rows]
    except asyncpg.UndefinedColumnError:
        return []


async def add_keywords_bulk(
    pool: asyncpg.Pool,
    words: list[str],
    group_id: Optional[int] = None,
    added_by: Optional[int] = None,
) -> tuple[int, int]:
    """
    Insert multiple keywords. Each word is normalized (strip, lower). Duplicates (in DB or in list) are skipped.
    Returns (added_count, skipped_count).
    """
    if not words:
        return (0, 0)
    seen: set[str] = set()
    unique_words: list[str] = []
    for w in words:
        x = (w or "").strip().lower()
        if x and x not in seen:
            seen.add(x)
            unique_words.append(x)
    if not unique_words:
        return (0, len(words))
    added = 0
    for w in unique_words:
        kid = await add_keyword(pool, w, added_by=added_by, group_id=group_id)
        if kid is not None:
            added += 1
    skipped = len(unique_words) - added
    return (added, skipped)


# --- target_channels (multiple target channels for publishing) ---


async def get_active_target_channels(pool: asyncpg.Pool) -> list[dict]:
    """Return list of active target channels (channel_identifier, display_name, id)."""
    try:
        rows = await pool.fetch(
            """
            SELECT id, channel_identifier, display_name
            FROM target_channels WHERE is_active = TRUE
            ORDER BY created_at
            """
        )
        return [dict(r) for r in rows]
    except asyncpg.UndefinedTableError:
        return []


async def get_all_target_channels(pool: asyncpg.Pool) -> list[dict]:
    """Return all target channels for admin list."""
    try:
        rows = await pool.fetch(
            """
            SELECT id, channel_identifier, display_name, is_active, created_at
            FROM target_channels ORDER BY created_at
            """
        )
        return [dict(r) for r in rows]
    except asyncpg.UndefinedTableError:
        return []


async def add_target_channel(
    pool: asyncpg.Pool,
    channel_identifier: str,
    added_by: Optional[int] = None,
    display_name: str = "",
) -> Optional[int]:
    """Insert target channel. Returns id or None on unique violation."""
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO target_channels (channel_identifier, display_name, added_by)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            channel_identifier.strip(),
            (display_name or "").strip(),
            added_by,
        )
        return row["id"] if row else None
    except (asyncpg.UniqueViolationError, asyncpg.UndefinedTableError):
        return None


async def remove_target_channel(pool: asyncpg.Pool, channel_id: int) -> bool:
    """Delete target channel by id. Returns True if deleted."""
    try:
        result = await pool.execute(
            "DELETE FROM target_channels WHERE id = $1",
            channel_id,
        )
        return result == "DELETE 1"
    except asyncpg.UndefinedTableError:
        return False


# --- config (target_channel) ---


async def get_config_value(pool: asyncpg.Pool, key: str) -> Optional[str]:
    """Get config value by key. Returns None if not found."""
    row = await pool.fetchrow(
        "SELECT value FROM config WHERE key = $1", key
    )
    return row["value"] if row else None


async def set_config_value(
    pool: asyncpg.Pool, key: str, value: str, description: Optional[str] = None
) -> None:
    """Set config value. Upserts (insert or update)."""
    if description is not None:
        await pool.execute(
            """
            INSERT INTO config (key, value, description, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (key) DO UPDATE SET value = $2, description = $3, updated_at = NOW()
            """,
            key,
            value,
            description,
        )
    else:
        await pool.execute(
            """
            INSERT INTO config (key, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()
            """,
            key,
            value,
        )


async def bootstrap_admin_editor(
    pool: asyncpg.Pool, user_id: int, username: str = ""
) -> None:
    """Ensure user_id is in both admins and editors (for initial EDITOR_CHAT_ID)."""
    await pool.execute(
        """
        INSERT INTO admins (user_id, username) VALUES ($1, $2)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id,
        (username or "").strip(),
    )
    await pool.execute(
        """
        INSERT INTO editors (user_id, username) VALUES ($1, $2)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id,
        (username or "").strip(),
    )
