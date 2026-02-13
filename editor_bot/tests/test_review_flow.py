"""Tests for approve/edit/reject flow (keyboard and callback_data)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.bot.keyboards import review_keyboard


def test_review_keyboard_has_three_actions() -> None:
    """Keyboard contains approve, edit, reject."""
    kb = review_keyboard(1)
    assert kb.inline_keyboard
    flat = [b for row in kb.inline_keyboard for b in row]
    assert len(flat) >= 3
    data = [b.callback_data for b in flat]
    assert "approve_1" in data
    assert "edit_1" in data
    assert "reject_1" in data


@pytest.mark.asyncio
async def test_reject_only_pending_review() -> None:
    """Reject should not update status when post is not pending_review."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    from src.bot.handlers.review import cb_reject
    from src.database.models import Post

    callback = MagicMock()
    callback.data = "reject_1"
    callback.from_user = MagicMock(id=123)
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_reply_markup = AsyncMock()

    pool = MagicMock()
    pool.execute = AsyncMock()
    data = {"pool": pool}

    published_post = Post(
        id=1,
        source_channel="test",
        source_message_id=1,
        original_text=None,
        pdf_path="/x.pdf",
        extracted_text=None,
        summary="x",
        edited_summary=None,
        editor_message_id=None,
        status="published",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    with patch("src.bot.handlers.review.get_post_by_id", new_callable=AsyncMock, return_value=published_post):
        await cb_reject(callback, data)

    callback.answer.assert_called_once()
    assert "обработан" in callback.answer.call_args[0][0].lower() or "не найден" in callback.answer.call_args[0][0].lower()
    pool.execute.assert_not_called()


@pytest.mark.asyncio
async def test_review_post_with_empty_pdf_path() -> None:
    """Post with pdf_path empty (text-only) is still loadable and rejectable."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    from src.bot.handlers.review import cb_reject
    from src.database.models import Post

    callback = MagicMock()
    callback.data = "reject_2"
    callback.from_user = MagicMock(id=123)
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_reply_markup = AsyncMock()

    pool = MagicMock()
    pool.execute = AsyncMock()
    data = {"pool": pool}

    text_only_post = Post(
        id=2,
        source_channel="test",
        source_message_id=2,
        original_text="Только текст",
        pdf_path="",
        extracted_text=None,
        summary="Summary",
        edited_summary=None,
        editor_message_id=None,
        status="pending_review",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    with patch("src.bot.handlers.review.get_post_by_id", new_callable=AsyncMock, return_value=text_only_post):
        await cb_reject(callback, data)
    callback.answer.assert_called_once()
    assert callback.answer.call_args[0][0] == "Отклонено."
    assert pool.execute.call_count >= 1


@pytest.mark.asyncio
async def test_claim_pending_for_publish_second_call_returns_false() -> None:
    """Two sequential claim_pending_for_publish: first returns True, second False (post already publishing)."""
    from src.database.repository import claim_pending_for_publish

    pool = MagicMock()
    pool.execute = AsyncMock(side_effect=["UPDATE 1", "UPDATE 0"])
    first = await claim_pending_for_publish(pool, post_id=10)
    second = await claim_pending_for_publish(pool, post_id=10)
    assert first is True
    assert second is False
    assert pool.execute.call_count == 2


@pytest.mark.asyncio
async def test_update_post_status_invalid_status_raises() -> None:
    """update_post_status with invalid status raises ValueError."""
    from src.database.repository import update_post_status

    pool = MagicMock()
    pool.execute = AsyncMock()
    with pytest.raises(ValueError) as exc_info:
        await update_post_status(pool, post_id=1, status="typo_status")
    assert "Invalid post status" in str(exc_info.value)
    assert "typo_status" in str(exc_info.value)
    pool.execute.assert_not_called()
