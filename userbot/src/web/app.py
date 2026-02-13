"""aiohttp app for internal API: POST /discussion/resolve."""

from typing import Optional

from aiohttp import web
import structlog
from telethon import TelegramClient

from src.services.discussion_resolver import resolve_discussion_message

log = structlog.get_logger()


def _check_auth(request: web.Request, expected_token: Optional[str]) -> bool:
    if not expected_token or not expected_token.strip():
        return True
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return False
    return auth[7:].strip() == expected_token.strip()


async def handle_discussion_resolve(request: web.Request) -> web.Response:
    """
    POST /discussion/resolve with JSON { "channel_id": "-100...", "message_id": 123 }.
    Returns { "ok": true, "discussion_chat_id": int, "discussion_message_id": int } or { "ok": false, "error": "..." }.
    """
    client: Optional[TelegramClient] = request.app.get("client")
    token = request.app.get("api_token") or ""

    if not _check_auth(request, token):
        log.warning("discussion_resolve_unauthorized", path=request.path)
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)
    if not client:
        return web.json_response({"ok": False, "error": "Server not ready"}, status=503)

    try:
        body = await request.json()
    except Exception as e:
        log.error("discussion_resolve_bad_json", error=str(e))
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    channel_id = body.get("channel_id")
    raw_msg_id = body.get("message_id")
    if channel_id is None or raw_msg_id is None:
        return web.json_response(
            {"ok": False, "error": "channel_id and message_id required"},
            status=400,
        )
    try:
        message_id = int(raw_msg_id)
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "message_id must be integer"}, status=400)
    if message_id < 1:
        return web.json_response({"ok": False, "error": "message_id must be positive"}, status=400)

    discussion_chat_id, discussion_message_id = await resolve_discussion_message(
        client, str(channel_id), message_id
    )
    if discussion_chat_id is None or discussion_message_id is None:
        return web.json_response(
            {"ok": False, "error": "Could not resolve discussion message"},
            status=200,
        )

    return web.json_response(
        {
            "ok": True,
            "discussion_chat_id": discussion_chat_id,
            "discussion_message_id": discussion_message_id,
        }
    )


def create_app(client: TelegramClient, api_token: Optional[str] = None) -> web.Application:
    app = web.Application()
    app["client"] = client
    app["api_token"] = api_token or ""
    app.router.add_post("/discussion/resolve", handle_discussion_resolve)
    return app
