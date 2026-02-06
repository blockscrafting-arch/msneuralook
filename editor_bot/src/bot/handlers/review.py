"""Handlers for approve / edit / reject buttons."""

from typing import Any

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.fsm.context import FSMContext
import structlog

from src.database.repository import add_audit_log, get_post_by_id, update_post_status
from src.bot.keyboards import review_keyboard
from src.bot.states import EditSummaryStates
from src.services.publisher import publish_to_channel

log = structlog.get_logger()

router = Router(name="review")


def _get_pool_from_data(data: dict[str, Any]):
    return data.get("pool")


async def _send_post_to_editor(
    bot: Bot,
    editor_chat_id: int,
    post_id: int,
    summary: str,
    pdf_path: str,
    pool,
) -> int | None:
    """Send summary text + PDF and keyboard to editor. Returns message_id or None."""
    text = f"Новый пост!\n\nТекст (саммари):\n{summary}"
    kb = review_keyboard(post_id)
    try:
        if pdf_path:
            # Send document (PDF) with caption and inline keyboard
            import os
            if os.path.isfile(pdf_path):
                doc = FSInputFile(pdf_path)
                msg = await bot.send_document(
                    editor_chat_id,
                    doc,
                    caption=text[:1024],
                    reply_markup=kb,
                )
            else:
                msg = await bot.send_message(editor_chat_id, text, reply_markup=kb)
        else:
            msg = await bot.send_message(editor_chat_id, text, reply_markup=kb)
        return msg.message_id
    except Exception as e:
        log.error("send_to_editor_failed", post_id=post_id, exc_info=True, error=str(e))
        return None


@router.callback_query(F.data.startswith("approve_"))
async def cb_approve(callback: CallbackQuery, bot: Bot, data: dict) -> None:
    """Publish post to target channel and update status."""
    pool = _get_pool_from_data(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    post_id = int(callback.data.split("_", 1)[1])
    post = await get_post_by_id(pool, post_id)
    if not post or post.status != "pending_review":
        await callback.answer("Пост уже обработан или не найден.", show_alert=True)
        return
    text = post.display_summary()
    try:
        await publish_to_channel(bot, data["target_channel_id"], text, post.pdf_path)
        await update_post_status(pool, post_id, "published")
        await add_audit_log(pool, post_id, "approved", actor=str(callback.from_user.id))
        await callback.answer("Опубликовано.")
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        log.error("publish_failed", post_id=post_id, exc_info=True, error=str(e))
        await callback.answer("Ошибка публикации.", show_alert=True)


@router.callback_query(F.data.startswith("reject_"))
async def cb_reject(callback: CallbackQuery, data: dict) -> None:
    """Mark post as rejected (only if still pending_review)."""
    pool = _get_pool_from_data(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    post_id = int(callback.data.split("_", 1)[1])
    post = await get_post_by_id(pool, post_id)
    if not post or post.status != "pending_review":
        await callback.answer("Пост уже обработан или не найден.", show_alert=True)
        return
    await update_post_status(pool, post_id, "rejected")
    await add_audit_log(pool, post_id, "rejected", actor=str(callback.from_user.id))
    await callback.answer("Отклонено.")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("edit_"))
async def cb_edit(callback: CallbackQuery, state: FSMContext, data: dict) -> None:
    """Ask editor to send new text, then re-show buttons."""
    pool = _get_pool_from_data(data)
    if not pool:
        await callback.answer("Ошибка сервера.", show_alert=True)
        return
    post_id = int(callback.data.split("_", 1)[1])
    post = await get_post_by_id(pool, post_id)
    if not post or post.status != "pending_review":
        await callback.answer("Пост уже обработан или не найден.", show_alert=True)
        return
    await state.update_data(editing_post_id=post_id)
    await state.set_state(EditSummaryStates.waiting_for_text)
    await callback.answer()
    await callback.message.answer("Введите новый текст саммари (одним сообщением):")


@router.message(EditSummaryStates.waiting_for_text, F.text)
async def process_edited_text(message: Message, state: FSMContext, bot: Bot, data: dict) -> None:
    """Save edited summary and re-send message with buttons."""
    pool = _get_pool_from_data(data)
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
    new_text = message.text or ""
    await update_post_status(pool, post_id, "pending_review", edited_summary=new_text)
    await add_audit_log(pool, post_id, "edited", actor=str(message.from_user.id))
    await state.clear()
    post = await get_post_by_id(pool, post_id)
    if post:
        text = (
            f"Пост #{post_id}\n\n"
            f"Обновлённый текст:\n{post.display_summary()}\n\n"
            f"Источник: {post.source_channel} / msg #{post.source_message_id}"
        )
        await message.answer(text, reply_markup=review_keyboard(post_id))
    else:
        await message.answer("Пост не найден.")
