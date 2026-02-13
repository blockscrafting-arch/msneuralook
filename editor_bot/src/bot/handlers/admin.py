"""Admin panel handlers: /admin, inline menu, FSM for sources/target/editors/admins."""

import html
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import structlog

from src.database.repository import add_audit_log, get_post_by_id, get_scheduled_posts_upcoming, update_post_status
from src.database.admin_repository import (
    add_admin,
    add_editor,
    add_keyword,
    add_keyword_group,
    add_keywords_bulk,
    add_source_channel,
    add_target_channel,
    get_admins_list,
    get_all_keywords,
    get_all_keyword_groups,
    get_all_source_channels,
    get_all_target_channels,
    get_config_value,
    get_editors_list,
    get_keyword_group_by_id,
    get_keywords_by_group_id,
    remove_admin,
    remove_editor,
    remove_keyword,
    remove_keyword_group,
    remove_source_channel,
    remove_target_channel,
    set_config_value,
)
from src.bot.admin_keyboards import (
    ADMIN_ADM,
    ADMIN_ADM_ADD,
    ADMIN_ADM_DEL,
    ADMIN_CLOSE,
    ADMIN_ED,
    ADMIN_ED_ADD,
    ADMIN_ED_DEL,
    ADMIN_KG,
    ADMIN_KG_ADD,
    ADMIN_KG_ADD_KW,
    ADMIN_KG_BULK,
    ADMIN_KG_DEL,
    ADMIN_KG_OPEN,
    ADMIN_KW,
    ADMIN_KW_ADD,
    ADMIN_KW_BULK,
    ADMIN_KW_DEL,
    ADMIN_MAIN,
    ADMIN_SCHED,
    ADMIN_SCHED_EDIT,
    ADMIN_SCHED_REFRESH,
    ADMIN_SRC,
    ADMIN_SRC_ADD,
    ADMIN_SRC_DEL,
    ADMIN_TGT,
    ADMIN_TGT_ADD,
    ADMIN_TGT_DEL,
    ADMIN_TGT_EDIT,
    ADMIN_PROMPT,
    ADMIN_PROMPT_EDIT,
    ADMIN_PROMPT_SHOW_FULL,
    ADMIN_PROMPT_RESET,
    admin_admins_keyboard,
    admin_editors_keyboard,
    admin_keyword_groups_keyboard,
    admin_keyword_group_detail_keyboard,
    admin_keywords_keyboard,
    admin_main_keyboard,
    admin_prompt_keyboard,
    admin_prompt_full_keyboard,
    admin_scheduled_list_keyboard,
    admin_sources_keyboard,
    admin_target_channels_keyboard,
    admin_target_keyboard,
    admin_choose_group_keyboard,
    admin_choose_target_channel_keyboard,
)
from src.bot.admin_states import AdminStates
from src.utils.text import split_text

log = structlog.get_logger()

router = Router(name="admin")

# Validation: channel id -100... or @username
CHANNEL_ID_PATTERN = re.compile(r"^(-100\d+)$|^(@[a-zA-Z0-9_]{5,32})$")


def _pool(data: dict[str, Any]):
    return data.get("pool")


def _super_admin_id(data: dict[str, Any]) -> int | None:
    return data.get("super_admin_id")


def _esc(s: str) -> str:
    """Escape for HTML to prevent injection (bot uses parse_mode=HTML)."""
    return html.escape(str(s), quote=True)


def _format_keyword_groups_text(groups: list) -> str:
    """Format keyword groups list for display (name → channel)."""
    text = "Группы маркеров:\n\n"
    for g in groups:
        name = g.get("name", "")
        ch = g.get("channel_display_name") or g.get("channel_identifier") or ""
        text += f"• {_esc(name)} → {_esc(ch)}\n"
    return text


def _normalize_channel_input(text: str) -> str | None:
    """Accept -100... or @channel. Return normalized string or None."""
    text = (text or "").strip()
    if not text:
        return None
    # Allow link form: t.me/channel -> @channel
    if "t.me/" in text:
        part = text.split("t.me/")[-1].split("?")[0].strip()
        if part:
            text = f"@{part}" if not part.startswith("@") else part
    if CHANNEL_ID_PATTERN.match(text):
        return text
    if text.startswith("@") and 5 <= len(text) <= 33:
        return text
    try:
        n = int(text)
        if n < 0:
            return str(n)
    except ValueError:
        pass
    return None


# --- /admin and main menu ---


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Open admin panel main menu."""
    data = kwargs
    await state.clear()
    await message.answer(
        "— Админ-панель —",
        reply_markup=admin_main_keyboard(),
    )


@router.callback_query(F.data == ADMIN_MAIN)
async def cb_admin_main(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Show main admin menu."""
    data = kwargs
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "— Админ-панель —",
        reply_markup=admin_main_keyboard(),
    )


@router.callback_query(F.data == ADMIN_CLOSE)
async def cb_admin_close(callback: CallbackQuery) -> None:
    """Close admin panel."""
    await callback.answer("Закрыто.")
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_text("Закрыто.", reply_markup=None)


# --- Source channels ---


@router.callback_query(F.data == ADMIN_SRC)
async def cb_admin_sources(callback: CallbackQuery, **kwargs: Any) -> None:
    """Show source channels list and keyboard."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    channels = await get_all_source_channels(pool)
    text = "Каналы-источники (мониторинг PDF):\n\n"
    if not channels:
        text += "Нет каналов. Нажмите «Добавить канал»."
    else:
        for ch in channels:
            ident = ch.get("channel_identifier", "")
            name = ch.get("display_name") or ident
            active = "✅" if ch.get("is_active") else "⏸"
            text += f"{active} {_esc(name)}\n  ({_esc(ident)})\n"
    await callback.message.edit_text(
        text,
        reply_markup=admin_sources_keyboard(channels),
    )


@router.callback_query(F.data == ADMIN_SRC_ADD)
async def cb_admin_src_add(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM: add source channel."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.adding_source_channel)
    await callback.message.answer(
        "Введите идентификатор канала: ID (например -1001234567890) или @username, или ссылку t.me/channel"
    )


@router.callback_query(F.data.startswith(ADMIN_SRC_DEL + "_"))
async def cb_admin_src_del(callback: CallbackQuery, **kwargs: Any) -> None:
    """Delete source channel by id."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    raw = callback.data[len(ADMIN_SRC_DEL) + 1 :].strip()
    try:
        cid = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    deleted = await remove_source_channel(pool, cid)
    if deleted:
        await add_audit_log(
            pool,
            None,
            "admin_remove_source_channel",
            actor=str(callback.from_user.id) if callback.from_user else None,
            details={"channel_id": cid},
        )
        await callback.answer("Канал удалён.")
        channels = await get_all_source_channels(pool)
        text = "Каналы-источники (мониторинг PDF):\n\n"
        if not channels:
            text += "Нет каналов. Нажмите «Добавить канал»."
        else:
            for ch in channels:
                ident = ch.get("channel_identifier", "")
                name = ch.get("display_name") or ident
                active = "✅" if ch.get("is_active") else "⏸"
                text += f"{active} {_esc(name)}\n  ({_esc(ident)})\n"
        await callback.message.edit_text(
            text,
            reply_markup=admin_sources_keyboard(channels),
        )
    else:
        await callback.answer("Канал не найден или уже удалён.", show_alert=True)


@router.message(AdminStates.adding_source_channel, F.text)
async def process_add_source_channel(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Process entered channel identifier and add to DB."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    raw = message.text or ""
    ident = _normalize_channel_input(raw)
    if not ident:
        await message.answer(
            "Неверный формат. Введите ID канала (например -1001234567890) или @username."
        )
        return
    added_id = await add_source_channel(
        pool,
        ident,
        added_by=message.from_user.id if message.from_user else None,
    )
    await state.clear()
    if added_id is not None:
        await add_audit_log(
            pool,
            None,
            "admin_add_source_channel",
            actor=str(message.from_user.id) if message.from_user else None,
            details={"channel_identifier": ident},
        )
        await message.answer(f"Канал {ident} добавлен.")
    else:
        await message.answer("Такой канал уже есть в списке.")


# --- Target channels ---


@router.callback_query(F.data == ADMIN_TGT)
async def cb_admin_target(callback: CallbackQuery, **kwargs: Any) -> None:
    """Show target channels list and keyboard."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    channels = await get_all_target_channels(pool)
    text = "Целевые каналы (публикация одобренных постов во все активные):\n\n"
    if not channels:
        text += "Нет каналов. Добавьте целевой канал. Если таблица не создана — выполните миграцию migrate_004_target_channels.sql."
    else:
        for ch in channels:
            ident = ch.get("channel_identifier", "")
            disp = ch.get("display_name") or ident
            active = "✓" if ch.get("is_active", True) else "✗"
            text += f"• {_esc(disp)} ({_esc(ident)}) {active}\n"
    await callback.message.edit_text(
        text,
        reply_markup=admin_target_channels_keyboard(channels),
    )


@router.callback_query(F.data == ADMIN_TGT_ADD)
async def cb_admin_tgt_add(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM: add target channel."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.adding_target_channel)
    await callback.message.answer(
        "Введите ID целевого канала (например -1001234567890) или @username:"
    )


@router.message(AdminStates.adding_target_channel, F.text)
async def process_add_target_channel(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Save new target channel to target_channels table."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    raw = message.text or ""
    ident = _normalize_channel_input(raw)
    if not ident:
        await message.answer(
            "Неверный формат. Введите ID канала (например -1001234567890) или @username."
        )
        return
    added = await add_target_channel(
        pool, ident, added_by=message.from_user.id if message.from_user else None
    )
    await state.clear()
    if added:
        await add_audit_log(
            pool,
            None,
            "admin_add_target_channel",
            actor=str(message.from_user.id) if message.from_user else None,
            details={"channel_identifier": ident},
        )
        await message.answer(f"Целевой канал добавлен: {_esc(ident)}")
    else:
        await message.answer("Такой канал уже в списке или ошибка БД.")


@router.callback_query(F.data.startswith(ADMIN_TGT_DEL + "_"))
async def cb_admin_tgt_del(callback: CallbackQuery, **kwargs: Any) -> None:
    """Remove target channel by id."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    raw = callback.data[len(ADMIN_TGT_DEL) + 1 :].strip()
    try:
        cid = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    deleted = await remove_target_channel(pool, cid)
    if deleted:
        await add_audit_log(
            pool,
            None,
            "admin_remove_target_channel",
            actor=str(callback.from_user.id) if callback.from_user else None,
            details={"channel_id": cid},
        )
        await callback.answer("Канал удалён.")
        channels = await get_all_target_channels(pool)
        text = "Целевые каналы (публикация одобренных постов во все активные):\n\n"
        if not channels:
            text += "Нет каналов. Добавьте целевой канал."
        else:
            for ch in channels:
                ident = ch.get("channel_identifier", "")
                disp = ch.get("display_name") or ident
                active = "✓" if ch.get("is_active", True) else "✗"
                text += f"• {_esc(disp)} ({_esc(ident)}) {active}\n"
        await callback.message.edit_text(
            text,
            reply_markup=admin_target_channels_keyboard(channels),
        )
    else:
        await callback.answer("Канал не найден или уже удалён.", show_alert=True)


@router.callback_query(F.data == ADMIN_TGT_EDIT)
async def cb_admin_tgt_edit(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM: change target channel (legacy config)."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.changing_target_channel)
    await callback.message.answer(
        "Введите ID целевого канала (например -1001234567890) или @username:"
    )


@router.message(AdminStates.changing_target_channel, F.text)
async def process_target_channel(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Save new target channel to config (legacy fallback)."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    raw = message.text or ""
    ident = _normalize_channel_input(raw)
    if not ident:
        await message.answer(
            "Неверный формат. Введите ID канала (например -1001234567890) или @username."
        )
        return
    await set_config_value(pool, "target_channel", ident, description="ID целевого канала для публикации")
    await state.clear()
    await add_audit_log(
        pool,
        None,
        "admin_set_target_channel",
        actor=str(message.from_user.id) if message.from_user else None,
        details={"target_channel": ident},
    )
    await message.answer(f"Целевой канал установлен: {_esc(ident)}")


# --- OpenAI prompt (config) ---


PROMPT_PREVIEW_LEN = 4000
DEFAULT_OPENAI_PROMPT = "Напиши краткое саммари текста для публикации в канале. Сохраняй смысл, будь лаконичен."


def _format_prompt_preview(prompt: str | None) -> str:
    """Format prompt for preview (truncate with …)."""
    if not prompt or not prompt.strip():
        return "(пусто — в n8n будет использован дефолтный промпт)"
    if len(prompt) > PROMPT_PREVIEW_LEN:
        return prompt[:PROMPT_PREVIEW_LEN].rstrip() + "…"
    return prompt


def _format_prompt_full(prompt: str | None) -> str:
    """Format prompt for full view (escape only; no length limit)."""
    if not prompt or not prompt.strip():
        return "(пусто)"
    return _esc(prompt)


@router.callback_query(F.data == ADMIN_PROMPT)
async def cb_admin_prompt(callback: CallbackQuery, **kwargs: Any) -> None:
    """Show current OpenAI prompt and keyboard."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    prompt = await get_config_value(pool, "openai_prompt")
    display = _format_prompt_preview(prompt)
    text = f"Текущий промпт OpenAI:\n\n{_esc(display)}"
    await callback.message.edit_text(
        text,
        reply_markup=admin_prompt_keyboard(),
    )


@router.callback_query(F.data == ADMIN_PROMPT_SHOW_FULL)
async def cb_admin_prompt_show_full(callback: CallbackQuery, **kwargs: Any) -> None:
    """Show full prompt text (by request), in multiple messages if needed."""
    data = kwargs
    pool = _pool(data)
    bot = data.get("bot")
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    if not bot:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    prompt = await get_config_value(pool, "openai_prompt")
    body = _format_prompt_full(prompt)
    text = f"Промпт OpenAI (полностью):\n\n{body}"
    chunks = split_text(text)
    if not chunks:
        chunks = [text]
    chat_id = callback.message.chat.id
    for i, chunk in enumerate(chunks):
        reply_markup = admin_prompt_full_keyboard() if i == len(chunks) - 1 else None
        await bot.send_message(chat_id, chunk, reply_markup=reply_markup)


@router.callback_query(F.data == ADMIN_PROMPT_RESET)
async def cb_admin_prompt_reset(callback: CallbackQuery, **kwargs: Any) -> None:
    """Reset OpenAI prompt to default."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await set_config_value(
        pool, "openai_prompt", DEFAULT_OPENAI_PROMPT, description="Промпт для OpenAI"
    )
    await add_audit_log(
        pool,
        None,
        "admin_reset_openai_prompt",
        actor=str(callback.from_user.id) if callback.from_user else None,
        details={},
    )
    await callback.answer("Промпт сброшен к дефолту.")
    display = _format_prompt_preview(DEFAULT_OPENAI_PROMPT)
    text = f"Текущий промпт OpenAI:\n\n{_esc(display)}"
    await callback.message.edit_text(
        text,
        reply_markup=admin_prompt_keyboard(),
    )


@router.callback_query(F.data == ADMIN_PROMPT_EDIT)
async def cb_admin_prompt_edit(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM: edit OpenAI prompt."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.editing_openai_prompt)
    await callback.message.answer(
        "Введите новый промпт для OpenAI (текст будет подставлен перед текстом поста):"
    )


@router.message(AdminStates.editing_openai_prompt, F.text)
async def process_openai_prompt(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Save new OpenAI prompt to config."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Промпт не может быть пустым. Введите текст.")
        return
    await set_config_value(
        pool, "openai_prompt", text, description="Промпт для OpenAI"
    )
    await state.clear()
    await add_audit_log(
        pool,
        None,
        "admin_set_openai_prompt",
        actor=str(message.from_user.id) if message.from_user else None,
        details={},
    )
    await message.answer("Промпт OpenAI обновлён.")


# --- Keywords (markers) ---


@router.callback_query(F.data == ADMIN_KW)
async def cb_admin_keywords(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Show keywords list and keyboard."""
    await state.clear()
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    keywords = await get_all_keywords(pool)
    text = "Слова-маркеры (посты из канала-источника попадают в обработку только если в тексте есть хотя бы один маркер):\n\n"
    if not keywords:
        text += "Нет маркеров. Если список пуст — все посты проходят. Добавьте маркер для фильтрации."
    else:
        for kw in keywords:
            text += f"• {_esc(kw.get('word', ''))}\n"
    await callback.message.edit_text(
        text,
        reply_markup=admin_keywords_keyboard(keywords),
    )


@router.callback_query(F.data == ADMIN_KW_ADD)
async def cb_admin_kw_add(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM: add keyword."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.adding_keyword)
    await callback.message.answer("Введите слово-маркер (одним словом или фраза):")


@router.message(AdminStates.adding_keyword, F.text)
async def process_add_keyword(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Save new keyword to DB."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    raw = (message.text or "").strip().lower()
    if not raw:
        await message.answer("Введите непустое слово.")
        return
    added = await add_keyword(
        pool, raw, added_by=message.from_user.id if message.from_user else None
    )
    await state.clear()
    if added:
        await add_audit_log(
            pool,
            None,
            "admin_add_keyword",
            actor=str(message.from_user.id) if message.from_user else None,
            details={"word": raw},
        )
        await message.answer(f"Маркер добавлен: {_esc(raw)}")
    else:
        await message.answer("Такой маркер уже есть или ошибка БД.")


@router.callback_query(F.data.startswith(ADMIN_KW_DEL + "_"))
async def cb_admin_kw_del(callback: CallbackQuery, **kwargs: Any) -> None:
    """Remove keyword by id."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    raw = callback.data[len(ADMIN_KW_DEL) + 1 :].strip()
    try:
        kid = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    deleted = await remove_keyword(pool, kid)
    if deleted:
        await add_audit_log(
            pool,
            None,
            "admin_remove_keyword",
            actor=str(callback.from_user.id) if callback.from_user else None,
            details={"keyword_id": kid},
        )
        await callback.answer("Маркер удалён.")
        keywords = await get_all_keywords(pool)
        text = "Слова-маркеры:\n\n"
        if not keywords:
            text += "Нет маркеров. Все посты проходят."
        else:
            for kw in keywords:
                text += f"• {_esc(kw.get('word', ''))}\n"
        await callback.message.edit_text(
            text,
            reply_markup=admin_keywords_keyboard(keywords),
        )
    else:
        await callback.answer("Маркер не найден или уже удалён.", show_alert=True)


@router.callback_query(F.data == "admin_noop")
async def cb_admin_noop(callback: CallbackQuery) -> None:
    """No-op for placeholder buttons."""
    await callback.answer()


# --- Keyword groups ---


@router.callback_query(F.data == ADMIN_KG)
async def cb_admin_keyword_groups(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Show keyword groups list."""
    await state.clear()
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    groups = await get_all_keyword_groups(pool)
    text = "Группы маркеров (каждая группа привязана к целевому каналу; при публикации пост уходит в каналы тех групп, маркеры которых есть в тексте):\n\n"
    if not groups:
        text += "Нет групп. Добавьте группу и привяжите к ней маркеры."
    else:
        for g in groups:
            name = g.get("name") or ""
            ch = g.get("channel_display_name") or g.get("channel_identifier") or ""
            text += f"• {_esc(name)} → {_esc(ch)}\n"
    await callback.message.edit_text(
        text,
        reply_markup=admin_keyword_groups_keyboard(groups),
    )


@router.callback_query(F.data == ADMIN_KG_ADD)
async def cb_admin_kg_add(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM: add keyword group — ask for name."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    channels = await get_all_target_channels(pool)
    if not channels:
        await callback.answer("Сначала добавьте целевой канал в «Целевые каналы».", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.adding_keyword_group)
    await callback.message.answer("Введите название группы маркеров (например: Нейронауки):")


@router.message(AdminStates.adding_keyword_group, F.text)
async def process_kg_name(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Save group name to state and ask to choose target channel."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Введите непустое название.")
        return
    await state.update_data(kg_name=name)
    await state.set_state(AdminStates.adding_keyword_group_choose_channel)
    channels = await get_all_target_channels(pool)
    await message.answer(
        "Выберите целевой канал для этой группы:",
        reply_markup=admin_choose_target_channel_keyboard(channels, back_data=ADMIN_KG),
    )


@router.callback_query(F.data.startswith("admin_tc_"), AdminStates.adding_keyword_group_choose_channel)
async def process_kg_choose_channel(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Save group with chosen target_channel_id."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    raw = callback.data.replace("admin_tc_", "").strip()
    try:
        tc_id = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    d = await state.get_data()
    name = d.get("kg_name") or ""
    if not name:
        await state.clear()
        await callback.answer("Сессия сброшена.", show_alert=True)
        return
    gid = await add_keyword_group(
        pool, name, tc_id, added_by=callback.from_user.id if callback.from_user else None
    )
    await state.clear()
    if gid:
        await add_audit_log(
            pool, None, "admin_add_keyword_group",
            actor=str(callback.from_user.id) if callback.from_user else None,
            details={"group_id": gid, "name": name},
        )
        await callback.answer(f"Группа «{_esc(name)}» создана.")
        groups = await get_all_keyword_groups(pool)
        await callback.message.edit_text(
            _format_keyword_groups_text(groups),
            reply_markup=admin_keyword_groups_keyboard(groups),
        )
    else:
        await callback.answer("Ошибка при создании группы.", show_alert=True)


@router.callback_query(
    (F.data.startswith(ADMIN_KG_OPEN + "_")) | (F.data.startswith(ADMIN_KG_ADD_KW + "_"))
)
async def cb_admin_kg_open(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Open one group: show name, channel, list of keywords. Callback: admin_kg_open_<id> or admin_kg_ak_<id>."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    is_add_kw = ADMIN_KG_ADD_KW in callback.data
    prefix = ADMIN_KG_ADD_KW + "_" if is_add_kw else ADMIN_KG_OPEN + "_"
    if not callback.data.startswith(prefix):
        await callback.answer()
        return
    raw = callback.data[len(prefix):].strip()
    try:
        gid = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    group = await get_keyword_group_by_id(pool, gid)
    if not group:
        await callback.answer("Группа не найдена.", show_alert=True)
        return
    if is_add_kw:
        await callback.answer()
        await state.update_data(adding_keyword_group_id=gid)
        await state.set_state(AdminStates.adding_keyword_to_group)
        await callback.message.answer(
            f"Введите слово-маркер для группы «{_esc(group.get('name', ''))}»:"
        )
        return
    keywords = await get_keywords_by_group_id(pool, gid)
    text = f"Группа: {_esc(group.get('name', ''))}\nКанал: {_esc(group.get('channel_display_name') or group.get('channel_identifier') or '')}\n\nМаркеры:\n"
    if not keywords:
        text += "Нет маркеров. Добавьте маркер в группу."
    else:
        for kw in keywords:
            text += f"• {_esc(kw.get('word', ''))}\n"
    await callback.answer()
    await callback.message.edit_text(
        text,
        reply_markup=admin_keyword_group_detail_keyboard(gid, keywords),
    )


@router.message(AdminStates.adding_keyword_to_group, F.text)
async def process_add_keyword_to_group(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Save keyword with group_id."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    d = await state.get_data()
    gid = d.get("adding_keyword_group_id")
    if gid is None:
        await state.clear()
        await message.answer("Сессия сброшена.")
        return
    raw = (message.text or "").strip().lower()
    if not raw:
        await message.answer("Введите непустое слово.")
        return
    added = await add_keyword(
        pool, raw,
        added_by=message.from_user.id if message.from_user else None,
        group_id=gid,
    )
    await state.clear()
    if added:
        await add_audit_log(
            pool, None, "admin_add_keyword",
            actor=str(message.from_user.id) if message.from_user else None,
            details={"word": raw, "group_id": gid},
        )
        await message.answer(f"Маркер добавлен в группу: {_esc(raw)}")
    else:
        await message.answer("Маркер не добавлен. Возможно, группа была удалена или такой маркер уже есть.")


@router.callback_query(F.data.startswith(ADMIN_KG_DEL + "_"))
async def cb_admin_kg_del(callback: CallbackQuery, **kwargs: Any) -> None:
    """Delete keyword group. Markers get group_id=NULL."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    raw = callback.data[len(ADMIN_KG_DEL) + 1 :].strip()
    try:
        gid = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    ok = await remove_keyword_group(pool, gid)
    if ok:
        await add_audit_log(
            pool, None, "admin_remove_keyword_group",
            actor=str(callback.from_user.id) if callback.from_user else None,
            details={"group_id": gid},
        )
        await callback.answer("Группа удалена. Маркеры остались без группы.")
        groups = await get_all_keyword_groups(pool)
        await callback.message.edit_text(
            _format_keyword_groups_text(groups),
            reply_markup=admin_keyword_groups_keyboard(groups),
        )
    else:
        await callback.answer("Группа не найдена.", show_alert=True)


# --- Bulk keywords ---


@router.callback_query(F.data.startswith(ADMIN_KG_BULK + "_"))
async def cb_admin_kg_bulk(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start bulk add for this group: set bulk_group_id and ask for list (no group choice)."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    raw = callback.data[len(ADMIN_KG_BULK) + 1 :].strip()
    try:
        gid = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    if gid < 1:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    group = await get_keyword_group_by_id(pool, gid)
    if not group:
        await callback.answer("Группа не найдена.", show_alert=True)
        return
    await state.update_data(bulk_group_id=gid)
    await state.set_state(AdminStates.adding_keywords_bulk)
    await callback.answer()
    await callback.message.answer("Введите список слов через запятую или с новой строки:")


@router.callback_query(F.data == ADMIN_KW_BULK)
async def cb_admin_kw_bulk(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start bulk add: if groups exist ask for group, else ask for list."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    groups = await get_all_keyword_groups(pool)
    if groups:
        await state.set_state(AdminStates.adding_keywords_bulk_choose_group)
        await callback.message.answer(
            "Выберите группу для новых маркеров (или «Без группы»):",
            reply_markup=admin_choose_group_keyboard(groups, with_none=True, back_data=ADMIN_KW),
        )
    else:
        await state.update_data(bulk_group_id=None)
        await state.set_state(AdminStates.adding_keywords_bulk)
        await callback.message.answer(
            "Введите список слов через запятую или с новой строки:"
        )


@router.callback_query(F.data.startswith("admin_gr_"), AdminStates.adding_keywords_bulk_choose_group)
async def process_bulk_choose_group(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Set group_id and ask for list."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    raw = callback.data.replace("admin_gr_", "").strip()
    try:
        gid = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    if gid != 0:
        groups = await get_all_keyword_groups(pool)
        if not any(g.get("id") == gid for g in groups):
            await callback.answer("Группа не найдена.", show_alert=True)
            return
    group_id = None if gid == 0 else gid
    await state.update_data(bulk_group_id=group_id)
    await state.set_state(AdminStates.adding_keywords_bulk)
    await callback.answer()
    await callback.message.answer("Введите список слов через запятую или с новой строки:")


@router.message(AdminStates.adding_keywords_bulk, F.text)
async def process_bulk_keywords(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Parse list, call add_keywords_bulk, report."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    d = await state.get_data()
    group_id = d.get("bulk_group_id")
    raw = message.text or ""
    parts = [p.strip().lower() for line in raw.replace(",", "\n").split("\n") for p in line.strip().split() if p.strip()]
    unique = list(dict.fromkeys(parts))
    if not unique:
        await message.answer("Не найдено ни одного слова. Введите слова через запятую или с новой строки.")
        return
    limit = 300
    if len(unique) > limit:
        unique = unique[:limit]
    added, skipped = await add_keywords_bulk(
        pool, unique, group_id=group_id,
        added_by=message.from_user.id if message.from_user else None,
    )
    await state.clear()
    total = len(unique)
    msg = f"Добавлено: {added}. Пропущено (дубликаты): {skipped}. Всего в сообщении: {total}."
    if group_id is not None and added == 0 and total > 0:
        msg += " Возможно, группа была удалена."
    await message.answer(msg)
    if added:
        await add_audit_log(
            pool, None, "admin_add_keywords_bulk",
            actor=str(message.from_user.id) if message.from_user else None,
            details={"added": added, "skipped": skipped, "group_id": group_id},
        )


# --- Scheduled list ---


def _format_scheduled_list(posts: list) -> str:
    """Format scheduled posts for display (MSK)."""
    if not posts:
        return "Нет запланированных постов."
    lines = []
    for p in posts:
        pid = getattr(p, "id", None) or p.get("id")
        sat = getattr(p, "scheduled_at", None) or p.get("scheduled_at")
        if sat:
            if hasattr(sat, "astimezone"):
                sat_msk = sat.astimezone(MSK)
            else:
                sat_msk = sat
            fmt = sat_msk.strftime("%d.%m.%Y %H:%M")
            lines.append(f"Пост #{pid} — {fmt} (МСК)")
        else:
            lines.append(f"Пост #{pid} — ?")
    return "План публикаций (МСК):\n\n" + "\n".join(lines)


@router.callback_query(F.data == ADMIN_SCHED)
async def cb_admin_scheduled(callback: CallbackQuery, **kwargs: Any) -> None:
    """Show list of scheduled posts with dates."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    posts = await get_scheduled_posts_upcoming(pool, limit=50)
    text = _format_scheduled_list(posts)
    await callback.message.edit_text(
        text,
        reply_markup=admin_scheduled_list_keyboard(posts=posts),
    )


@router.callback_query(F.data == ADMIN_SCHED_REFRESH)
async def cb_admin_scheduled_refresh(callback: CallbackQuery, **kwargs: Any) -> None:
    """Refresh scheduled list."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer("Обновлено.")
    posts = await get_scheduled_posts_upcoming(pool, limit=50)
    text = _format_scheduled_list(posts)
    try:
        await callback.message.edit_text(text, reply_markup=admin_scheduled_list_keyboard(posts=posts))
    except Exception:
        pass


# Pattern for scheduled datetime (DD.MM.YYYY HH:MM), same as in review
_SCHEDULE_PATTERN = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})$")


@router.callback_query(F.data.startswith(ADMIN_SCHED_EDIT + "_"))
async def cb_admin_sched_edit(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM to edit scheduled time for a post."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    raw = callback.data[len(ADMIN_SCHED_EDIT) + 1 :].strip()
    try:
        post_id = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    if post_id < 1:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    post = await get_post_by_id(pool, post_id)
    if not post or getattr(post, "status", None) != "scheduled":
        await callback.answer("Пост не найден или не в статусе «запланирован».", show_alert=True)
        return
    await state.update_data(editing_scheduled_post_id=post_id)
    await state.set_state(AdminStates.editing_scheduled_time)
    await callback.answer()
    await callback.message.answer(
        "Введите новую дату и время (МСК), например 15.02.2026 14:00"
    )


@router.message(AdminStates.editing_scheduled_time, F.text)
async def process_editing_scheduled_time(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Parse new datetime (MSK), update scheduled_at, confirm."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    d = await state.get_data()
    post_id = d.get("editing_scheduled_post_id")
    if not post_id:
        await message.answer("Сессия сброшена. Выберите пост заново в «Отложенные посты».")
        await state.clear()
        return
    raw = (message.text or "").strip()
    m = _SCHEDULE_PATTERN.match(raw)
    if not m:
        await message.answer(
            "Неверный формат. Введите ДД.ММ.ГГГГ ЧЧ:ММ (например 15.02.2026 14:00)."
        )
        return
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hour, minute = int(m.group(4)), int(m.group(5))
    try:
        dt_msk = datetime(year, month, day, hour, minute, tzinfo=MSK)
    except ValueError:
        await message.answer("Некорректная дата или время.")
        return
    dt_utc = dt_msk.astimezone(timezone.utc)
    if dt_utc <= datetime.now(timezone.utc):
        await message.answer("Укажите время в будущем (МСК).")
        return
    await update_post_status(pool, post_id, "scheduled", scheduled_at=dt_utc)
    await add_audit_log(
        pool, post_id, "admin_reschedule",
        actor=str(message.from_user.id) if message.from_user else None,
        details={"scheduled_at": dt_utc.isoformat()},
    )
    await state.clear()
    fmt = dt_msk.strftime("%d.%m.%Y %H:%M")
    await message.answer(f"Время поста #{post_id} изменено на {fmt} (МСК).")
    posts = await get_scheduled_posts_upcoming(pool, limit=50)
    text = _format_scheduled_list(posts)
    await message.answer(text, reply_markup=admin_scheduled_list_keyboard(posts=posts))


# --- Editors ---


@router.callback_query(F.data == ADMIN_ED)
async def cb_admin_editors(callback: CallbackQuery, **kwargs: Any) -> None:
    """Show editors list and keyboard."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    editors = await get_editors_list(pool)
    super_id = _super_admin_id(data)
    text = "Редакторы (могут утверждать/редактировать/отклонять посты):\n\n"
    if not editors:
        text += "Нет редакторов. Добавьте первого."
    else:
        for ed in editors:
            uid = ed.get("user_id")
            un = ed.get("username") or ""
            label = f"@{_esc(un)}" if un else str(uid)
            main = " (главный)" if uid == super_id else ""
            text += f"• {label}{main}\n"
    await callback.message.edit_text(
        text,
        reply_markup=admin_editors_keyboard(editors, super_admin_id=super_id),
    )


@router.callback_query(F.data == "admin_ed_noop")
async def cb_admin_ed_noop(callback: CallbackQuery) -> None:
    """Cannot remove super admin."""
    await callback.answer("Главного редактора нельзя удалить.", show_alert=True)


@router.callback_query(F.data == ADMIN_ED_ADD)
async def cb_admin_ed_add(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM: add editor."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.adding_editor)
    await callback.message.answer(
        "Перешлите сообщение от пользователя или введите его Telegram ID (число):"
    )


@router.callback_query(F.data.startswith(ADMIN_ED_DEL + "_"))
async def cb_admin_ed_del(callback: CallbackQuery, **kwargs: Any) -> None:
    """Remove editor by user_id. Cannot remove super_admin."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    super_id = _super_admin_id(data)
    raw = callback.data[len(ADMIN_ED_DEL) + 1 :].strip()
    try:
        uid = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    if uid == super_id:
        await callback.answer("Главного редактора нельзя удалить.", show_alert=True)
        return
    deleted = await remove_editor(pool, uid)
    if deleted:
        await add_audit_log(
            pool,
            None,
            "admin_remove_editor",
            actor=str(callback.from_user.id) if callback.from_user else None,
            details={"user_id": uid},
        )
        await callback.answer("Редактор удалён.")
        editors = await get_editors_list(pool)
        text = "Редакторы:\n\n"
        for ed in editors:
            uid_ = ed.get("user_id")
            un = ed.get("username") or ""
            label = f"@{_esc(un)}" if un else str(uid_)
            main = " (главный)" if uid_ == super_id else ""
            text += f"• {label}{main}\n"
        await callback.message.edit_text(
            text,
            reply_markup=admin_editors_keyboard(editors, super_admin_id=super_id),
        )
    else:
        await callback.answer("Редактор не найден.", show_alert=True)


@router.message(AdminStates.adding_editor, F.text)
@router.message(AdminStates.adding_editor, F.forward_from)
async def process_add_editor(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Add editor by forwarded message or numeric user id."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    user_id = None
    username = ""
    if message.forward_from:
        user_id = message.forward_from.id
        username = (message.forward_from.username or "").strip()
    elif message.text:
        try:
            user_id = int(message.text.strip())
        except ValueError:
            await message.answer("Введите число (Telegram user ID) или перешлите сообщение от пользователя.")
            return
    if user_id is None:
        await message.answer("Не удалось определить пользователя. Перешлите его сообщение или введите ID.")
        await state.clear()
        return
    await state.clear()
    ok = await add_editor(
        pool,
        user_id,
        username=username,
        added_by=message.from_user.id if message.from_user else None,
    )
    if ok:
        await add_audit_log(
            pool,
            None,
            "admin_add_editor",
            actor=str(message.from_user.id) if message.from_user else None,
            details={"user_id": user_id},
        )
        await message.answer(f"Редактор добавлен: {user_id}" + (f" (@{_esc(username)})" if username else ""))
    else:
        await message.answer("Пользователь уже в списке редакторов.")


# --- Admins ---


@router.callback_query(F.data == ADMIN_ADM)
async def cb_admin_admins(callback: CallbackQuery, **kwargs: Any) -> None:
    """Show admins list and keyboard."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    admins_list = await get_admins_list(pool)
    super_id = _super_admin_id(data)
    text = "Админы (доступ к этой панели):\n\n"
    if not admins_list:
        text += "Нет админов."
    else:
        for ad in admins_list:
            uid = ad.get("user_id")
            un = ad.get("username") or ""
            label = f"@{_esc(un)}" if un else str(uid)
            main = " (главный)" if uid == super_id else ""
            text += f"• {label}{main}\n"
    await callback.message.edit_text(
        text,
        reply_markup=admin_admins_keyboard(admins_list, super_admin_id=super_id),
    )


@router.callback_query(F.data == "admin_adm_noop")
async def cb_admin_adm_noop(callback: CallbackQuery) -> None:
    """Cannot remove super admin."""
    await callback.answer("Главного админа нельзя удалить.", show_alert=True)


@router.callback_query(F.data == ADMIN_ADM_ADD)
async def cb_admin_adm_add(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM: add admin."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.adding_admin)
    await callback.message.answer(
        "Перешлите сообщение от пользователя или введите его Telegram ID (число):"
    )


@router.callback_query(F.data.startswith(ADMIN_ADM_DEL + "_"))
async def cb_admin_adm_del(callback: CallbackQuery, **kwargs: Any) -> None:
    """Remove admin by user_id. Cannot remove super_admin."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    super_id = _super_admin_id(data)
    raw = callback.data[len(ADMIN_ADM_DEL) + 1 :].strip()
    try:
        uid = int(raw)
    except ValueError:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    if uid == super_id:
        await callback.answer("Главного админа нельзя удалить.", show_alert=True)
        return
    deleted = await remove_admin(pool, uid)
    if deleted:
        await add_audit_log(
            pool,
            None,
            "admin_remove_admin",
            actor=str(callback.from_user.id) if callback.from_user else None,
            details={"user_id": uid},
        )
        await callback.answer("Админ удалён.")
        admins_list = await get_admins_list(pool)
        text = "Админы:\n\n"
        for ad in admins_list:
            uid_ = ad.get("user_id")
            un = ad.get("username") or ""
            label = f"@{_esc(un)}" if un else str(uid_)
            main = " (главный)" if uid_ == super_id else ""
            text += f"• {label}{main}\n"
        await callback.message.edit_text(
            text,
            reply_markup=admin_admins_keyboard(admins_list, super_admin_id=super_id),
        )
    else:
        await callback.answer("Админ не найден.", show_alert=True)


@router.message(AdminStates.adding_admin, F.text)
@router.message(AdminStates.adding_admin, F.forward_from)
async def process_add_admin(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Add admin by forwarded message or numeric user id."""
    data = kwargs
    pool = _pool(data)
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    user_id = None
    username = ""
    if message.forward_from:
        user_id = message.forward_from.id
        username = (message.forward_from.username or "").strip()
    elif message.text:
        try:
            user_id = int(message.text.strip())
        except ValueError:
            await message.answer("Введите число (Telegram user ID) или перешлите сообщение от пользователя.")
            return
    if user_id is None:
        await message.answer("Не удалось определить пользователя. Перешлите его сообщение или введите ID.")
        await state.clear()
        return
    await state.clear()
    ok = await add_admin(
        pool,
        user_id,
        username=username,
        added_by=message.from_user.id if message.from_user else None,
    )
    if ok:
        await add_audit_log(
            pool,
            None,
            "admin_add_admin",
            actor=str(message.from_user.id) if message.from_user else None,
            details={"user_id": user_id},
        )
        await message.answer(f"Админ добавлен: {user_id}" + (f" (@{_esc(username)})" if username else ""))
    else:
        await message.answer("Пользователь уже в списке админов.")
