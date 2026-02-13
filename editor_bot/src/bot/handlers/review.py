"""Handlers for approve / edit / reject / schedule buttons."""

import html
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.fsm.context import FSMContext
import structlog

from src.database.repository import (
    add_audit_log,
    claim_pending_for_publish,
    clear_scheduled_return_to_pending,
    get_post_by_id,
    update_post_status,
)
from src.database.admin_repository import get_channel_ids_for_publish, get_config_value
from src.bot.keyboards import review_keyboard, schedule_actions_keyboard
from src.bot.states import EditSummaryStates, ScheduleStates
from src.services.publisher import publish_to_all_channels
from src.utils.text import split_text, strip_markdown_asterisks, SUMMARY_MAX_LENGTH

MSK = ZoneInfo("Europe/Moscow")
SCHEDULE_PATTERN = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})$")

log = structlog.get_logger()

router = Router(name="review")


def _get_pool_from_data(data: dict[str, Any]):
    return data.get("pool")


def _parse_post_id_from_callback(callback_data: str, prefix: str) -> int | None:
    """Extract post_id from callback.data (e.g. 'approve_123'). Returns None if invalid."""
    if not callback_data.startswith(prefix) or len(callback_data) <= len(prefix):
        return None
    try:
        n = int(callback_data[len(prefix):].strip())
        return n if n >= 1 else None
    except ValueError:
        return None


async def _send_post_to_editor(
    bot: Bot,
    editor_chat_id: int,
    post_id: int,
    summary: str,
    pdf_path: str,
    pool,
) -> int | None:
    """Send full summary (chunked if needed) with keyboard, then PDF as reply to first message. Returns message_id of first message or None."""
    text = f"Новый пост!\n\nТекст (саммари):\n{html.escape(strip_markdown_asterisks(summary or ''))}"
    chunks = split_text(text) or [text]
    kb = review_keyboard(post_id)
    try:
        import os
        msg = await bot.send_message(editor_chat_id, chunks[0], reply_markup=kb)
        for part in chunks[1:]:
            await bot.send_message(editor_chat_id, part)
        if pdf_path and os.path.isfile(pdf_path):
            await bot.send_document(
                editor_chat_id,
                FSInputFile(pdf_path),
                caption=f"PDF к посту #{post_id}",
                reply_to_message_id=msg.message_id,
            )
        return msg.message_id
    except Exception as e:
        log.error("send_to_editor_failed", post_id=post_id, exc_info=True, error=str(e))
        return None


@router.callback_query(F.data.startswith("approve_"))
async def cb_approve(callback: CallbackQuery, **kwargs: Any) -> None:
    """Publish post to target channel and update status."""
    data = kwargs
    pool = data.get("pool")
    bot = data.get("bot")
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    if not bot:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    post_id = _parse_post_id_from_callback(callback.data, "approve_")
    if not post_id:
        await callback.answer("Неверные данные кнопки.", show_alert=True)
        return
    post = await get_post_by_id(pool, post_id)
    if not post:
        await callback.answer("Пост не найден.", show_alert=True)
        return
    # Разрешаем processing: редактор уже видит пост (доставка могла ещё не обновить БД)
    if post.status not in ("pending_review", "publishing", "processing"):
        log.warning(
            "approve_rejected_status",
            post_id=post_id,
            status=post.status,
            msg="Editor clicked Publish but post status is not publishable",
        )
        await callback.answer("Пост уже обработан или не найден.", show_alert=True)
        return
    text_for_routing = (post.original_text or "") + " " + (post.display_summary() or "")
    fallback = await get_config_value(pool, "target_channel") or data.get("target_channel_id") or ""
    channel_ids = await get_channel_ids_for_publish(
        pool, text_for_routing, fallback_channel_from_config=fallback.strip() or None
    )
    if not channel_ids:
        log.warning("approve_no_target_channel", post_id=post_id)
        await callback.answer("Не задан целевой канал. Укажите в админке.", show_alert=True)
        return
    updated = await claim_pending_for_publish(pool, post_id)
    if not updated:
        post_after = await get_post_by_id(pool, post_id)
        log.warning(
            "approve_claim_failed",
            post_id=post_id,
            status_after=post_after.status if post_after else None,
            msg="Another editor may have published or status changed",
        )
        if post_after and post_after.status in ("processing", "publishing"):
            await callback.answer("Пост ещё доставляется редакторам, подождите.", show_alert=True)
        else:
            await callback.answer("Пост уже обработан или не найден.", show_alert=True)
        return
    await callback.answer("Публикуем…")
    text = post.display_summary()
    try:
        await publish_to_all_channels(
            bot,
            channel_ids,
            text,
            post.pdf_path or "",
            data.get("pdf_storage_path", "/data/pdfs"),
            userbot_api_url=data.get("userbot_api_url"),
            userbot_api_token=data.get("userbot_api_token"),
        )
        await update_post_status(pool, post_id, "published")
        log.info("approve_published", post_id=post_id, editor_id=callback.from_user.id if callback.from_user else None)
        await add_audit_log(pool, post_id, "approved", actor=str(callback.from_user.id) if callback.from_user else None)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    except Exception as e:
        log.error("publish_failed", post_id=post_id, exc_info=True, error=str(e))
        await update_post_status(pool, post_id, "pending_review")
        await bot.send_message(
            callback.message.chat.id,
            "Ошибка публикации. Пост возвращён на утверждение.",
        )
        alert_chat_id = data.get("alert_chat_id")
        if alert_chat_id:
            from src.utils.alert import send_alert
            await send_alert(
                bot,
                alert_chat_id,
                f"⚠️ Ошибка публикации поста #{post_id}: {e!s}"[:4000],
                "publish_failed",
            )


@router.callback_query(F.data.startswith("schedule_"))
async def cb_schedule(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Ask editor for schedule datetime, then save as scheduled."""
    data = kwargs
    pool = data.get("pool")
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    post_id = _parse_post_id_from_callback(callback.data, "schedule_")
    if not post_id:
        await callback.answer("Неверные данные кнопки.", show_alert=True)
        return
    post = await get_post_by_id(pool, post_id)
    if not post or post.status != "pending_review":
        await callback.answer("Пост уже обработан или не найден.", show_alert=True)
        return
    await state.update_data(scheduling_post_id=post_id)
    await state.set_state(ScheduleStates.waiting_for_datetime)
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "Введите дату и время публикации (МСК), формат ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Например: 15.02.2026 14:00"
    )


@router.message(ScheduleStates.waiting_for_datetime, F.text)
async def process_schedule_datetime(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Parse datetime (MSK), save scheduled_at, set status scheduled."""
    data = kwargs
    pool = data.get("pool")
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    d = await state.get_data()
    post_id = d.get("scheduling_post_id")
    if not post_id:
        await message.answer("Сессия сброшена. Выберите пост заново.")
        await state.clear()
        return
    raw = (message.text or "").strip()
    m = SCHEDULE_PATTERN.match(raw)
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
        pool, post_id, "scheduled",
        actor=str(message.from_user.id) if message.from_user else None,
        details={"scheduled_at": dt_utc.isoformat()},
    )
    await state.clear()
    fmt = dt_msk.strftime("%d.%m.%Y %H:%M")
    await message.answer(
        f"Пост #{post_id} запланирован на {fmt} (МСК). Статус: запланирован.",
        reply_markup=schedule_actions_keyboard(post_id),
    )


@router.callback_query(F.data.startswith("cancel_schedule_"))
async def cb_cancel_schedule(callback: CallbackQuery, **kwargs: Any) -> None:
    """Cancel scheduling: set post back to pending_review, clear scheduled_at."""
    data = kwargs
    pool = data.get("pool")
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    post_id = _parse_post_id_from_callback(callback.data, "cancel_schedule_")
    if not post_id:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    ok = await clear_scheduled_return_to_pending(pool, post_id)
    if not ok:
        await callback.answer("Пост не найден или уже не запланирован.", show_alert=True)
        return
    await add_audit_log(
        pool,
        post_id,
        "schedule_cancelled",
        actor=str(callback.from_user.id) if callback.from_user else None,
        details={},
    )
    await callback.answer("Планирование отменено, пост снова на утверждении.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Планирование отменено. Пост возвращён в очередь на утверждение.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("reschedule_"))
async def cb_reschedule(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Start FSM to enter new datetime for already scheduled post."""
    data = kwargs
    pool = data.get("pool")
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    post_id = _parse_post_id_from_callback(callback.data, "reschedule_")
    if not post_id:
        await callback.answer("Неверные данные.", show_alert=True)
        return
    post = await get_post_by_id(pool, post_id)
    if not post or post.status != "scheduled":
        await callback.answer("Пост не найден или не в статусе «запланирован».", show_alert=True)
        return
    await state.update_data(scheduling_post_id=post_id)
    await state.set_state(ScheduleStates.waiting_for_datetime)
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "Введите новую дату и время публикации (МСК), формат ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Например: 15.02.2026 14:00"
    )


@router.callback_query(F.data.startswith("reject_"))
async def cb_reject(callback: CallbackQuery, **kwargs: Any) -> None:
    """Mark post as rejected (only if still pending_review)."""
    data = kwargs
    pool = data.get("pool")
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    post_id = _parse_post_id_from_callback(callback.data, "reject_")
    if not post_id:
        await callback.answer("Неверные данные кнопки.", show_alert=True)
        return
    post = await get_post_by_id(pool, post_id)
    if not post or post.status != "pending_review":
        await callback.answer("Пост уже обработан или не найден.", show_alert=True)
        return
    await update_post_status(pool, post_id, "rejected")
    await add_audit_log(pool, post_id, "rejected", actor=str(callback.from_user.id) if callback.from_user else None)
    await callback.answer("Отклонено.")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("edit_"))
async def cb_edit(callback: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    """Ask editor to send new text, then re-show buttons."""
    data = kwargs
    pool = data.get("pool")
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    post_id = _parse_post_id_from_callback(callback.data, "edit_")
    if not post_id:
        await callback.answer("Неверные данные кнопки.", show_alert=True)
        return
    post = await get_post_by_id(pool, post_id)
    if not post or post.status != "pending_review":
        await callback.answer("Пост уже обработан или не найден.", show_alert=True)
        return
    await state.update_data(editing_post_id=post_id)
    await state.set_state(EditSummaryStates.waiting_for_text)
    await callback.answer()
    await callback.message.answer("Введите новый текст саммари (одним сообщением):")


@router.message(EditSummaryStates.waiting_for_text, F.text)
async def process_edited_text(message: Message, state: FSMContext, **kwargs: Any) -> None:
    """Save edited summary and re-send message with buttons."""
    data = kwargs
    pool = data.get("pool")
    if not pool:
        await message.answer("Ошибка сервера.")
        await state.clear()
        return
    d = await state.get_data()
    post_id = d.get("editing_post_id")
    if not post_id:
        await message.answer("Сессия сброшена. Выберите пост заново.")
        await state.clear()
        return
    raw_text = message.text or ""
    new_text = raw_text[:SUMMARY_MAX_LENGTH]
    if len(raw_text) > SUMMARY_MAX_LENGTH:
        await message.answer(f"Текст обрезан до {SUMMARY_MAX_LENGTH} символов.")
    await update_post_status(pool, post_id, "pending_review", edited_summary=new_text)
    await add_audit_log(pool, post_id, "edited", actor=str(message.from_user.id) if message.from_user else None)
    await state.clear()
    post = await get_post_by_id(pool, post_id)
    if post:
        text = (
            f"Пост #{post_id}\n\n"
            f"Обновлённый текст:\n{html.escape(strip_markdown_asterisks(post.display_summary() or ''))}\n\n"
            f"Источник: {post.source_channel} / msg #{post.source_message_id}"
        )
        await message.answer(text, reply_markup=review_keyboard(post_id))
    else:
        await message.answer("Пост не найден.")
