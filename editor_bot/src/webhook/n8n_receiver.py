"""aiohttp endpoint for POST from n8n with post data."""

from aiohttp import web
import structlog

from src.database.repository import add_audit_log, get_post_by_id, update_post_status

log = structlog.get_logger()


def _check_webhook_auth(request: web.Request, expected_token: str) -> bool:
    """Return True if Authorization: Bearer <expected_token> matches or expected_token is empty."""
    if not expected_token or not expected_token.strip():
        return True
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return False
    return auth[7:].strip() == expected_token.strip()


async def handle_incoming_post(request: web.Request) -> web.Response:
    """
    Accept POST from n8n: { post_id, summary, pdf_path, original_text }.
    Requires Authorization: Bearer <EDITOR_BOT_WEBHOOK_TOKEN> when token is set.
    Load post from DB, send message to editor with buttons, update editor_message_id.
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
    post_id = body.get("post_id")
    summary = body.get("summary") or ""
    pdf_path = body.get("pdf_path") or ""
    original_text = body.get("original_text") or ""
    if post_id is None:
        return web.json_response({"ok": False, "error": "post_id required"}, status=400)
    pool = request.app.get("pool")
    bot = request.app.get("bot")
    editor_chat_id = request.app.get("editor_chat_id")
    if not pool or not bot or editor_chat_id is None:
        log.error("incoming_post_missing_app_state")
        return web.json_response({"ok": False, "error": "Server not ready"}, status=503)
    post = await get_post_by_id(pool, post_id)
    if not post:
        return web.json_response({"ok": False, "error": "post not found"}, status=404)
    text = (
        f"Пост #{post_id}\n\n"
        f"Саммари:\n{summary}\n\n"
        f"Источник: {post.source_channel} / msg #{post.source_message_id}"
    )
    from src.bot.keyboards import review_keyboard
    kb = review_keyboard(post_id)
    try:
        import os
        from aiogram.types import FSInputFile
        if pdf_path and os.path.isfile(pdf_path):
            doc = FSInputFile(pdf_path)
            msg = await bot.send_document(
                editor_chat_id,
                doc,
                caption=text[:1024],
                reply_markup=kb,
            )
        else:
            msg = await bot.send_message(editor_chat_id, text, reply_markup=kb)
        await update_post_status(
            pool,
            post_id,
            "pending_review",
            editor_message_id=msg.message_id,
        )
        await add_audit_log(pool, post_id, "sent_to_editor")
        return web.json_response({"ok": True, "post_id": post_id})
    except Exception as e:
        log.error("incoming_post_send_failed", post_id=post_id, exc_info=True, error=str(e))
        return web.json_response({"ok": False, "error": str(e)}, status=500)


def create_app(pool, bot, editor_chat_id: int, webhook_path: str, webhook_token: str = "") -> web.Application:
    """Create aiohttp app with POST route for n8n."""
    app = web.Application()
    app["pool"] = pool
    app["bot"] = bot
    app["editor_chat_id"] = editor_chat_id
    app["webhook_token"] = webhook_token
    app.router.add_post(webhook_path.rstrip("/") or "/incoming/post", handle_incoming_post)
    return app
