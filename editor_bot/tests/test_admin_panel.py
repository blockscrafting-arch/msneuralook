"""Tests for admin panel: AdminPanelMiddleware, Admin button, cancel scheduled."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot.admin_keyboards import ADMIN_ED, ADMIN_SCHED_CANCEL, editor_admin_keyboard
from src.bot.middlewares import AdminPanelMiddleware


@pytest.mark.asyncio
async def test_admin_panel_middleware_blocks_editor_on_admin_ed() -> None:
    """Editor (not admin) on callback admin_ed gets answer and handler is not called."""
    from aiogram.types import CallbackQuery, User

    pool = MagicMock()
    editor_ids = {111}
    admin_ids = {222}
    with patch("src.bot.middlewares.get_editor_user_ids", new_callable=AsyncMock, return_value=editor_ids), \
         patch("src.bot.middlewares.get_admin_user_ids", new_callable=AsyncMock, return_value=admin_ids):
        mw = AdminPanelMiddleware(pool, super_admin_id=None)
        handler = AsyncMock(return_value=None)
        user = User(id=111, is_bot=False, first_name="Editor")
        event = CallbackQuery(id="cb1", from_user=user, chat_instance="c1", data="admin_ed")
        event.answer = AsyncMock()
        data = {}
        await mw(handler, event, data)
    event.answer.assert_called_once()
    assert "администраторов" in event.answer.call_args[0][0].lower()
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_admin_panel_middleware_allows_editor_on_admin_src() -> None:
    """Editor on callback admin_src passes to handler."""
    from aiogram.types import CallbackQuery, User

    pool = MagicMock()
    editor_ids = {111}
    admin_ids = {222}
    with patch("src.bot.middlewares.get_editor_user_ids", new_callable=AsyncMock, return_value=editor_ids), \
         patch("src.bot.middlewares.get_admin_user_ids", new_callable=AsyncMock, return_value=admin_ids):
        mw = AdminPanelMiddleware(pool, super_admin_id=None)
        handler = AsyncMock(return_value=None)
        user = User(id=111, is_bot=False, first_name="Editor")
        event = CallbackQuery(id="cb2", from_user=user, chat_instance="c2", data="admin_src")
        event.answer = AsyncMock()
        data = {}
        await mw(handler, event, data)
    handler.assert_called_once()


def test_editor_admin_keyboard_has_no_editors_admins() -> None:
    """Limited menu has no Редакторы/Админы buttons."""
    kb = editor_admin_keyboard()
    flat = [b for row in kb.inline_keyboard for b in row]
    data = [b.callback_data for b in flat]
    assert ADMIN_ED not in data
    assert "admin_adm" not in data


@pytest.mark.asyncio
async def test_admin_button_returns_limited_menu_when_not_admin() -> None:
    """When user is not admin, admin button handler returns editor_admin_keyboard (no admin_ed)."""
    from src.bot.handlers.commands import cmd_admin_button

    message = MagicMock()
    message.from_user = MagicMock(id=999)
    message.answer = AsyncMock()
    pool = MagicMock()
    with patch("src.bot.handlers.commands.is_admin", new_callable=AsyncMock, return_value=False):
        await cmd_admin_button(message, pool=pool)
    message.answer.assert_called_once()
    reply_markup = message.answer.call_args[1]["reply_markup"]
    flat = [b for row in reply_markup.inline_keyboard for b in row]
    data = [b.callback_data for b in flat]
    assert ADMIN_ED not in data


@pytest.mark.asyncio
async def test_admin_button_returns_full_menu_when_admin() -> None:
    """When user is admin, admin button handler returns keyboard with admin_ed."""
    from src.bot.handlers.commands import cmd_admin_button

    message = MagicMock()
    message.from_user = MagicMock(id=1)
    message.answer = AsyncMock()
    pool = MagicMock()
    with patch("src.bot.handlers.commands.is_admin", new_callable=AsyncMock, return_value=True):
        await cmd_admin_button(message, pool=pool)
    message.answer.assert_called_once()
    reply_markup = message.answer.call_args[1]["reply_markup"]
    flat = [b for row in reply_markup.inline_keyboard for b in row]
    data = [b.callback_data for b in flat]
    assert ADMIN_ED in data


@pytest.mark.asyncio
async def test_cb_admin_sched_cancel_calls_clear_and_audit() -> None:
    """Cancel scheduled: clear_scheduled_return_to_pending and add_audit_log called; list refreshed."""
    from src.bot.handlers.admin import cb_admin_sched_cancel

    callback = MagicMock()
    callback.data = f"{ADMIN_SCHED_CANCEL}_123"
    callback.from_user = MagicMock(id=456)
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="UPDATE 1")
    data = {"pool": pool}

    with patch(
        "src.bot.handlers.admin.clear_scheduled_return_to_pending",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_clear, \
    patch("src.bot.handlers.admin.add_audit_log", new_callable=AsyncMock()) as mock_audit, \
    patch(
        "src.bot.handlers.admin.get_scheduled_posts_upcoming",
        new_callable=AsyncMock,
        return_value=[],
    ):
        await cb_admin_sched_cancel(callback, **data)

    mock_clear.assert_called_once_with(pool, 123)
    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][2] == "admin_schedule_cancelled"
    callback.answer.assert_called_once()
    assert "отменена" in callback.answer.call_args[0][0].lower()
    callback.message.edit_text.assert_called_once()
