"""Send POST request to n8n webhook with post data."""

from typing import Any

import aiohttp
import structlog

log = structlog.get_logger()


async def send_to_n8n_webhook(
    webhook_url: str,
    *,
    post_text: str,
    pdf_path: str,
    message_id: int,
    channel_id: str | int,
    source_channel: str,
) -> bool:
    """
    Send new post data to n8n webhook.

    Args:
        webhook_url: Full URL of the n8n webhook (e.g. https://n8n.neurascope.pro/webhook/xxx).
        post_text: Text of the Telegram post.
        pdf_path: Path to the downloaded PDF file (filename or path for n8n to read).
        message_id: Telegram message ID.
        channel_id: Telegram channel/chat ID (string or int).
        source_channel: Source channel identifier (username or ID string).

    Returns:
        True if request succeeded (2xx), False otherwise.
    """
    payload: dict[str, Any] = {
        "post_text": post_text or "",
        "pdf_path": pdf_path,
        "message_id": message_id,
        "channel_id": str(channel_id),
        "source_channel": source_channel,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status >= 200 and resp.status < 300:
                    log.info(
                        "webhook_sent",
                        url=webhook_url,
                        message_id=message_id,
                        status=resp.status,
                    )
                    return True
                body = await resp.text()
                log.error(
                    "webhook_failed",
                    url=webhook_url,
                    message_id=message_id,
                    status=resp.status,
                    body=body[:500],
                )
                return False
    except aiohttp.ClientError as e:
        log.error(
            "webhook_request_error",
            url=webhook_url,
            message_id=message_id,
            exc_info=True,
            error=str(e),
        )
        return False
    except Exception as e:
        log.error(
            "webhook_unexpected_error",
            message_id=message_id,
            exc_info=True,
            error=str(e),
        )
        return False
