"""Client for userbot internal API: resolve discussion message id."""

from typing import Tuple

import aiohttp
import structlog

log = structlog.get_logger()


async def resolve_discussion(
    base_url: str,
    token: str,
    channel_id: str,
    message_id: int,
    timeout: float = 60.0,
) -> Tuple[int | None, int | None]:
    """
    Call userbot POST /discussion/resolve and return (discussion_chat_id, discussion_message_id).

    Returns (None, None) on any failure (network, 4xx/5xx, ok: false).
    """
    base_url = (base_url or "").rstrip("/")
    if not base_url:
        return None, None
    url = f"{base_url}/discussion/resolve"
    headers = {}
    if (token or "").strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    payload = {"channel_id": channel_id, "message_id": message_id}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    log.warning(
                        "discussion_resolve_http",
                        url=url,
                        status=resp.status,
                        channel_id=channel_id,
                        message_id=message_id,
                    )
                    return None, None
                data = await resp.json()
                if not data.get("ok"):
                    log.debug(
                        "discussion_resolve_not_ok",
                        channel_id=channel_id,
                        message_id=message_id,
                        error=data.get("error"),
                    )
                    return None, None
                cid = data.get("discussion_chat_id")
                mid = data.get("discussion_message_id")
                if cid is None or mid is None:
                    return None, None
                try:
                    return int(cid), int(mid)
                except (ValueError, TypeError):
                    return None, None
    except Exception as e:
        log.warning(
            "discussion_resolve_error",
            url=url,
            channel_id=channel_id,
            message_id=message_id,
            error=str(e),
        )
        return None, None
