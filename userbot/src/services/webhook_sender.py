"""Send POST request to n8n webhook with post data."""

import asyncio
import json
from typing import Any

import aiohttp
import structlog

log = structlog.get_logger()

# Retry delays in seconds (exponential backoff)
WEBHOOK_RETRY_DELAYS = (1, 3, 5)


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
    Send new post data to n8n webhook. Retries only on 5xx (not on 504); 504 is treated as accepted.
    Retry delays: 1, 3, 5 s.

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
    last_error: Exception | None = None
    for attempt, delay in enumerate(WEBHOOK_RETRY_DELAYS):
        if attempt > 0:
            log.info(
                "webhook_retry",
                url=webhook_url,
                message_id=message_id,
                attempt=attempt + 1,
                delay=delay,
            )
            await asyncio.sleep(delay)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=400),
                ) as resp:
                    if resp.status >= 200 and resp.status < 300:
                        body = await resp.text()
                        try:
                            data = json.loads(body) if body.strip() else {}
                            if data.get("ok") is False and data.get("error") == "notify_failed":
                                log.warning(
                                    "webhook_ack_but_notify_failed",
                                    url=webhook_url,
                                    message_id=message_id,
                                    status=resp.status,
                                    body=body[:200],
                                )
                                return False
                        except Exception:
                            pass
                        log.info(
                            "webhook_sent",
                            url=webhook_url,
                            message_id=message_id,
                            status=resp.status,
                            attempt=attempt + 1,
                        )
                        return True
                    if resp.status == 504:
                        body = await resp.text()
                        last_error = RuntimeError(f"HTTP 504: {body[:200]}")
                        log.warning(
                            "webhook_504_retry",
                            url=webhook_url,
                            message_id=message_id,
                            attempt=attempt + 1,
                        )
                        if attempt >= len(WEBHOOK_RETRY_DELAYS) - 1:
                            return False
                        continue
                    body = await resp.text()
                    last_error = RuntimeError(f"HTTP {resp.status}: {body[:200]}")
                    log.warning(
                        "webhook_failed",
                        url=webhook_url,
                        message_id=message_id,
                        status=resp.status,
                        body=body[:500],
                        attempt=attempt + 1,
                    )
                    if resp.status < 500:
                        return False
        except aiohttp.ClientError as e:
            last_error = e
            log.warning(
                "webhook_request_error",
                url=webhook_url,
                message_id=message_id,
                attempt=attempt + 1,
                error=str(e),
            )
        except Exception as e:
            last_error = e
            log.warning(
                "webhook_unexpected_error",
                message_id=message_id,
                attempt=attempt + 1,
                error=str(e),
            )
    log.error(
        "webhook_all_retries_failed",
        url=webhook_url,
        message_id=message_id,
        error=str(last_error),
    )
    return False
