"""Tests for admin_repository (keyword groups, add_keyword, FK handling)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

import asyncpg

from src.database.admin_repository import add_keyword


@pytest.mark.asyncio
async def test_add_keyword_returns_none_on_foreign_key_violation() -> None:
    """When group_id references non-existent group, add_keyword returns None (no exception)."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        side_effect=asyncpg.ForeignKeyViolationError("fk_keyword_groups")
    )
    result = await add_keyword(
        pool, "testword",
        added_by=123,
        group_id=99999,
    )
    assert result is None
    pool.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_add_keyword_returns_none_on_unique_violation() -> None:
    """When keyword already exists, add_keyword returns None."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=asyncpg.UniqueViolationError("unique_word"))
    result = await add_keyword(pool, "existing", added_by=1, group_id=None)
    assert result is None


@pytest.mark.asyncio
async def test_add_keyword_returns_id_on_success_with_group_id() -> None:
    """When group_id is valid and word is unique, add_keyword returns inserted id."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"id": 42})
    result = await add_keyword(
        pool, "newword",
        added_by=1,
        group_id=10,
    )
    assert result == 42
    pool.fetchrow.assert_called_once()
