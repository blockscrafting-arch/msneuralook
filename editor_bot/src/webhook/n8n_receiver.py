"""aiohttp endpoint for POST from n8n with post data."""

import asyncio
import html
import os
import secrets
from typing import Any, List, Optional

import asyncpg
from aiohttp import web
from aiogram import Bot
from aiogram.types import FSInputFile
import structlog

from src.bot.keyboards import review_keyboard
from src.database.repository import (
    add_audit_log,
    get_post_by_id,
    update_post_status,
    update_post_delivery_failed,
)
from src.database.admin_repository import get_editors_list
from src.utils.text import split_text, strip_markdown_asterisks, SUMMARY_MAX_LENGTH

log = structlog.get_logger()

# Generic message for 500 to avoid leaking internal details
HTTP_500_MESSAGE = "Internal server error"

# Timeout for sending text to a single editor (seconds)
SEND_TO_EDITOR_TIMEOUT = 90
# Timeout for sending PDF document (seconds)
SEND_PDF_TIMEOUT = 300
# Max request body size for webhook (bytes); larger bodies get 413
WEBHOOK_CLIENT_MAX_SIZE = 1024 * 1024  # 1 MiB
# Max post_id to avoid overflowing Telegram callback_data (64 bytes) and noisy logs
POST_ID_MAX = 2_000_000_000

_webhook_lock = asyncio.Lock()
# Посты, которые уже отправляются редакторам (webhook или scheduler) — не запускать второй раз
_post_ids_sending: set[int] = set()
_sending_lock = asyncio.Lock()
# В каждый момент только один пост отправляется редакторам (избегаем конкуренции за соединение)
_serial_send_lock = asyncio.Lock()


def _log_background_task_exception(task: asyncio.Task) -> None:
    """Done callback: retrieve and log any exception so it is not 'never retrieved'."""
    try:
        exc = task.exception()
        if exc is not None:
            log.error(
                "send_to_editors_background_failed",
                error=str(exc),
                exc_info=(type(exc), exc, exc.__traceback__),
            )
    except asyncio.CancelledError:
        pass


def _is_pdf_path_safe(pdf_path: str, allowed_base: str) -> bool:
    """Return True if pdf_path is under allowed_base and has no path traversal."""
    if not pdf_path or ".." in pdf_path:
        return False
    try:
        base = os.path.realpath(allowed_base)
        resolved = os.path.realpath(pdf_path)
        return resolved.startswith(base)
    except (OSError, ValueError):
        return False


def _check_webhook_auth(request: web.Request, expected_token: str) -> bool:
    """Return True only if Authorization: Bearer matches expected_token. Empty token => reject (403)."""
    if not expected_token or not expected_token.strip():
        return False
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return False
    return secrets.compare_digest(auth[7:].strip(), expected_token.strip())


def _is_retriable_pdf_error(e: Exception) -> bool:
    """True if PDF send failed due to timeout or connection/pipe error and retry may help."""
    if isinstance(e, asyncio.TimeoutError):
        return True
    if isinstance(e, ConnectionError):
        return True
    if isinstance(e, OSError) and getattr(e, "errno", None) == 32:
        return True
    s = str(e).lower()
    return (
        "timeout" in s
        or "broken pipe" in s
        or "connection lost" in s
        or "server disconnected" in s
        or "disconnect" in s
    )


async def _send_to_one_editor(
    bot: Bot,
    chat_id: int,
    chunks: List[str],
    kb: Any,
    post_id: int,
    pdf_path: str,
    use_pdf_file: bool,
) -> Optional[int]:
    """Send message chunks once, then optional PDF (up to 2 attempts with one retry on retriable errors).
    Returns first message_id or None on text failure. Text is never retried. On PDF failure we still return first_message_id."""
    if not chunks:
        return None
    log.info("incoming_post_send_to_editor_start", post_id=post_id, chat_id=chat_id)
    try:
        msg = await asyncio.wait_for(
            bot.send_message(chat_id, chunks[0], reply_markup=kb),
            timeout=SEND_TO_EDITOR_TIMEOUT,
        )
        first_message_id = msg.message_id
        for part in chunks[1:]:
            await asyncio.wait_for(
                bot.send_message(chat_id, part),
                timeout=SEND_TO_EDITOR_TIMEOUT,
            )
    except asyncio.TimeoutError:
        log.warning(
            "incoming_post_send_to_editor_failed",
            post_id=post_id,
            chat_id=chat_id,
            error="Timeout sending text to editor",
            timeout_seconds=SEND_TO_EDITOR_TIMEOUT,
        )
        return None
    except Exception as e:
        err = str(e).lower()
        if (
            "can't initiate" in err
            or "initiate conversation" in err
            or "chat not found" in err
            or "user not found" in err
            or "blocked" in err
        ):
            log.info(
                "incoming_post_editor_skip",
                post_id=post_id,
                chat_id=chat_id,
                reason="editor_hasnt_started_bot_or_unavailable",
            )
            return None
        log.warning(
            "incoming_post_send_to_editor_failed",
            post_id=post_id,
            chat_id=chat_id,
            error=str(e),
        )
        return None

    had_pdf = False
    if use_pdf_file and pdf_path:
        for attempt in range(1, 3):
            try:
                await asyncio.wait_for(
                    bot.send_document(
                        chat_id,
                        FSInputFile(pdf_path),
                        caption=f"PDF к посту #{post_id}",
                        reply_to_message_id=first_message_id,
                    ),
                    timeout=SEND_PDF_TIMEOUT,
                )
                had_pdf = True
                break
            except asyncio.TimeoutError as e:
                if attempt == 1 and _is_retriable_pdf_error(e):
                    log.warning(
                        "incoming_post_pdf_retry",
                        post_id=post_id,
                        chat_id=chat_id,
                        attempt=2,
                        reason="timeout",
                    )
                    await asyncio.sleep(2)
                else:
                    log.warning(
                        "incoming_post_pdf_send_failed",
                        post_id=post_id,
                        chat_id=chat_id,
                        attempt=attempt,
                        error="Timeout sending PDF",
                        timeout_seconds=SEND_PDF_TIMEOUT,
                    )
                    break
            except Exception as e:
                if attempt == 1 and _is_retriable_pdf_error(e):
                    log.warning(
                        "incoming_post_pdf_retry",
                        post_id=post_id,
                        chat_id=chat_id,
                        attempt=2,
                        reason="connection_error",
                    )
                    await asyncio.sleep(2)
                else:
                    log.warning(
                        "incoming_post_pdf_send_failed",
                        post_id=post_id,
                        chat_id=chat_id,
                        attempt=attempt,
                        error=str(e),
                    )
                    break

    log.info(
        "incoming_post_sent_to_editor",
        post_id=post_id,
        chat_id=chat_id,
        had_pdf=had_pdf,
    )
    return first_message_id


async def _send_to_editors_background(
    pool: asyncpg.Pool,
    bot: Bot,
    post_id: int,
    summary: str,
    pdf_path: str,
    pdf_storage_path: str,
    recipient_ids: List[int],
    alert_chat_id: Optional[int] = None,
) -> None:
    """
    Background task: load post, send to all editors, update status and audit_log.
    Exceptions are caught and logged so the event loop is not affected.
    Один и тот же post_id не отправляется параллельно (webhook + scheduler).
    """
    async with _sending_lock:
        if post_id in _post_ids_sending:
            log.info("incoming_post_send_skipped_already_sending", post_id=post_id)
            return
        _post_ids_sending.add(post_id)
    remaining_editors: List[int] = []
    chunks: List[str] = []
    kb = None
    use_pdf_file = False
    first_message_id = None
    async with _serial_send_lock:
        try:
            post = await get_post_by_id(pool, post_id)
            if not post:
                log.error("incoming_post_background_post_not_found", post_id=post_id)
                return
            if post.status not in ("processing", "send_failed") or post.editor_message_id is not None:
                log.info(
                    "incoming_post_duplicate_skipped",
                    post_id=post_id,
                    status=post.status,
                )
                return

            use_pdf_file = (
                pdf_path
                and _is_pdf_path_safe(pdf_path, pdf_storage_path)
                and os.path.isfile(pdf_path)
            )
            log.info(
                "incoming_post_send_start",
                post_id=post_id,
                pdf_path=pdf_path or "(empty)",
                recipient_count=len(recipient_ids),
                use_pdf_file=use_pdf_file,
            )
            if pdf_path and not use_pdf_file:
                if not pdf_path.strip():
                    reason = "path_empty"
                elif not _is_pdf_path_safe(pdf_path, pdf_storage_path):
                    reason = "path_not_safe"
                else:
                    reason = "file_not_found"
                log.warning(
                    "incoming_post_pdf_file_missing",
                    post_id=post_id,
                    pdf_path=pdf_path,
                    reason=reason,
                )
            summary_safe = html.escape(strip_markdown_asterisks(summary or ""))
            text = (
                f"Пост #{post_id}\n\n"
                f"Саммари:\n{summary_safe}\n\n"
                f"Источник: {post.source_channel} / msg #{post.source_message_id}"
            )
            chunks = split_text(text)
            if not chunks:
                chunks = [text]
            kb = review_keyboard(post_id)
            # Отправляем до первого успеха под lock; остальных шлём после освобождения lock
            first_message_id = None
            success_count = 0
            for i, chat_id in enumerate(recipient_ids):
                msg_id = await _send_to_one_editor(
                    bot, chat_id, chunks, kb, post_id, pdf_path, use_pdf_file
                )
                if msg_id is not None:
                    if first_message_id is None:
                        first_message_id = msg_id
                        success_count = 1
                        await update_post_status(
                            pool,
                            post_id,
                            "pending_review",
                            editor_message_id=first_message_id,
                        )
                        await add_audit_log(pool, post_id, "sent_to_editor")
                        remaining_editors = list(recipient_ids[i + 1 :])
                        break
                    success_count += 1
                await asyncio.sleep(1.0)

            if first_message_id is None:
                new_attempts = post.delivery_attempts + 1
                log.error(
                    "incoming_post_send_failed",
                    post_id=post_id,
                    recipient_count=len(recipient_ids),
                    all_failed=True,
                    delivery_attempts=new_attempts,
                )
                await update_post_delivery_failed(
                    pool,
                    post_id,
                    error="all editors failed or timed out",
                    attempts=new_attempts,
                )
                await add_audit_log(pool, post_id, "send_to_editor_failed")
                if alert_chat_id and new_attempts >= 5:
                    from src.utils.alert import send_alert
                    await send_alert(
                        bot,
                        alert_chat_id,
                        f"⚠️ Пост #{post_id} не удалось доставить ни одному редактору после 5 попыток.",
                        "delivery_failed",
                    )
                return
            log.info(
                "incoming_post_send_done",
                post_id=post_id,
                success_count=success_count,
                first_message_id=first_message_id,
            )
        except Exception as e:
            log.error(
                "incoming_post_background_error",
                post_id=post_id,
                error=str(e),
                exc_info=True,
            )
            try:
                audit_details = (
                    {"partial": True, "reason": "exception_after_first_success"}
                    if first_message_id is not None
                    else None
                )
                await add_audit_log(pool, post_id, "send_to_editor_failed", details=audit_details)
            except Exception:
                pass
        finally:
            # Всегда снимаем post_id с «в отправке»: нормальный выход, ранний return или исключение
            _post_ids_sending.discard(post_id)

    # Остальным редакторам шлём без удержания lock — очередь постов уже не ждёт
    for chat_id in remaining_editors:
        await _send_to_one_editor(
            bot, chat_id, chunks, kb, post_id, pdf_path, use_pdf_file
        )
        await asyncio.sleep(1.0)


async def handle_incoming_post(request: web.Request) -> web.Response:
    """
    Accept POST from n8n: { post_id, summary, pdf_path, original_text }.
    Requires Authorization: Bearer <EDITOR_BOT_WEBHOOK_TOKEN> when token is set.
    Load post from DB, send message to all editors (from admin panel) with buttons,
    update editor_message_id from first successful send.
    """
    webhook_token = request.app.get("webhook_token")
    if not _check_webhook_auth(request, webhook_token or ""):
        log.warning("webhook_unauthorized", path=request.path)
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)
    try:
        body = await request.json()
    except Exception as e:
        log.error("incoming_post_bad_json", exc_info=True, error=str(e))
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    raw_post_id = body.get("post_id")
    summary = (body.get("summary") or "")[:SUMMARY_MAX_LENGTH]
    pdf_path = body.get("pdf_path") or ""
    original_text = body.get("original_text") or ""
    if raw_post_id is None:
        return web.json_response({"ok": False, "error": "post_id required"}, status=400)
    try:
        post_id = int(raw_post_id)
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "post_id must be integer"}, status=400)
    if post_id < 1:
        return web.json_response({"ok": False, "error": "post_id must be positive"}, status=400)
    if post_id > POST_ID_MAX:
        return web.json_response({"ok": False, "error": "post_id too large"}, status=400)
    pool = request.app.get("pool")
    bot = request.app.get("bot")
    if not pool or not bot:
        log.error("incoming_post_missing_app_state")
        return web.json_response({"ok": False, "error": "Server not ready"}, status=503)
    editors = await get_editors_list(pool)
    if not editors:
        log.error("incoming_post_no_editors")
        return web.json_response({"ok": False, "error": "No editors configured"}, status=503)
    recipient_ids = [ed["user_id"] for ed in editors]

    async with _webhook_lock:
        post = await get_post_by_id(pool, post_id)
        if not post:
            return web.json_response({"ok": False, "error": "post not found"}, status=404)
        if post.status != "processing" or post.editor_message_id is not None:
            log.info("incoming_post_duplicate_skipped", post_id=post_id, status=post.status)
            return web.json_response({"ok": True, "post_id": post_id, "already_sent": True})

        pdf_storage_path = request.app.get("pdf_storage_path") or "/data/pdfs"
        alert_chat_id = request.app.get("alert_chat_id")
        task = asyncio.create_task(
            _send_to_editors_background(
                pool,
                bot,
                post_id,
                summary,
                pdf_path,
                pdf_storage_path,
                recipient_ids,
                alert_chat_id=alert_chat_id,
            )
        )
        task.add_done_callback(_log_background_task_exception)
    return web.json_response({"ok": True, "post_id": post_id})


def create_app(
    pool: asyncpg.Pool,
    bot: Bot,
    editor_chat_id: Optional[int],
    webhook_path: str,
    webhook_token: str = "",
    pdf_storage_path: str = "/data/pdfs",
    alert_chat_id: Optional[int] = None,
) -> web.Application:
    """Create aiohttp app with POST route for n8n. Recipients are all editors from DB (editor_chat_id unused)."""
    app = web.Application(client_max_size=WEBHOOK_CLIENT_MAX_SIZE)
    app["pool"] = pool
    app["bot"] = bot
    app["editor_chat_id"] = editor_chat_id
    app["webhook_token"] = webhook_token
    app["pdf_storage_path"] = pdf_storage_path.rstrip("/") or "/data/pdfs"
    app["alert_chat_id"] = alert_chat_id
    app.router.add_post(webhook_path.rstrip("/") or "/incoming/post", handle_incoming_post)
    return app
