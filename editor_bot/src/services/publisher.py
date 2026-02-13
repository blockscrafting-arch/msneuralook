"""Publish approved post to target Telegram channel."""

import asyncio
import html
import os
from typing import Any, Callable, Coroutine

from aiogram import Bot
from aiogram.types import FSInputFile
import structlog

from src.utils.text import split_text, strip_markdown_asterisks
from src.services.discussion_client import resolve_discussion

log = structlog.get_logger()

# Pause between publishing to different channels (seconds) to reduce rate-limit risk
PUBLISH_DELAY_BETWEEN_CHANNELS = 1.0
# Delay before sending PDF to discussion so Telegram can link the post (seconds)
PUBLISH_DELAY_BEFORE_PDF = 2.0
# Retries when sending PDF to discussion (Broken pipe / connection errors)
PUBLISH_DISCUSSION_RETRIES = 3
PUBLISH_DISCUSSION_RETRY_DELAY = 2.0

_publish_lock = asyncio.Lock()


def _is_retriable_discussion_error(e: Exception) -> bool:
    """True if send to discussion failed due to timeout/connection/pipe error and retry may help."""
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


def _is_retriable_channel_error(e: Exception) -> bool:
    """True if send to channel failed due to timeout/connection and retry may help."""
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


def _is_path_safe(pdf_path: str, allowed_base: str) -> bool:
    """Ensure pdf_path is under allowed_base and contains no path traversal."""
    if not pdf_path or ".." in pdf_path:
        return False
    base = os.path.realpath(allowed_base)
    try:
        resolved = os.path.realpath(pdf_path)
        return resolved.startswith(base)
    except (OSError, ValueError):
        return False


async def _send_with_retry(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run coroutine once; on FloodWait (retry_after) sleep and run again. Other exceptions propagate."""
    try:
        return await coro
    except Exception as e:
        retry_after = getattr(e, "retry_after", None)
        if retry_after is not None:
            log.warning("publish_flood_wait", retry_after=retry_after)
            await asyncio.sleep(float(retry_after))
            return await coro
        raise


async def _send_channel_with_retry(
    coro_factory: Callable[[], Coroutine[Any, Any, Any]],
) -> Any:
    """Run coro from factory; on timeout/connection error retry once. FloodWait handled inside."""
    for attempt in range(1, 3):
        try:
            return await _send_with_retry(coro_factory())
        except Exception as e:
            if attempt == 1 and _is_retriable_channel_error(e):
                log.warning(
                    "publish_channel_send_retry",
                    attempt=2,
                    error=str(e),
                )
                await asyncio.sleep(PUBLISH_DISCUSSION_RETRY_DELAY)
            else:
                raise
    raise AssertionError("unreachable")


async def publish_to_channel(
    bot: Bot,
    target_channel_id: str,
    caption: str,
    pdf_path: str,
    pdf_storage_path: str = "/data/pdfs",
    userbot_api_url: str | None = None,
    userbot_api_token: str | None = None,
) -> None:
    """
    Send caption (summary) in chunks and PDF to the target channel.
    If userbot_api_url is set, resolves discussion message via MTProto and sends PDF in linked group.
    Otherwise or on resolve failure, PDF is sent in channel as reply to post.
    Each send is retried once on FloodWait.
    """
    channel = target_channel_id.strip()
    if not channel:
        raise ValueError("TARGET_CHANNEL_ID is empty")
    if pdf_path.strip() and not _is_path_safe(pdf_path, pdf_storage_path):
        raise ValueError("pdf_path is outside allowed storage directory")

    caption = html.escape(strip_markdown_asterisks(caption or ""))
    chunks = split_text(caption) or [caption]
    first_msg = await _send_channel_with_retry(lambda: bot.send_message(channel, chunks[0]))
    channel_message_id = first_msg.message_id
    for part in chunks[1:]:
        await _send_channel_with_retry(lambda p=part: bot.send_message(channel, p))

    if pdf_path and os.path.isfile(pdf_path):
        await asyncio.sleep(PUBLISH_DELAY_BEFORE_PDF)
        discussion_chat_id: int | None = None
        discussion_message_id: int | None = None
        if (userbot_api_url or "").strip():
            discussion_chat_id, discussion_message_id = await resolve_discussion(
                userbot_api_url.strip(),
                (userbot_api_token or "").strip(),
                channel,
                channel_message_id,
            )
        if discussion_chat_id is not None and discussion_message_id is not None:
            last_error: Exception | None = None
            for attempt in range(PUBLISH_DISCUSSION_RETRIES):
                try:
                    await _send_with_retry(
                        bot.send_document(
                            discussion_chat_id,
                            FSInputFile(pdf_path),
                            reply_to_message_id=discussion_message_id,
                        )
                    )
                    log.info("published_to_channel", channel=channel, pdf_path=pdf_path, pdf_in_discussion=True)
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    if attempt < PUBLISH_DISCUSSION_RETRIES - 1 and _is_retriable_discussion_error(e):
                        log.warning(
                            "publish_pdf_to_discussion_retry",
                            channel=channel,
                            attempt=attempt + 1,
                            max_attempts=PUBLISH_DISCUSSION_RETRIES,
                            error=str(e),
                        )
                        await asyncio.sleep(PUBLISH_DISCUSSION_RETRY_DELAY)
                    else:
                        break
            if last_error is not None:
                log.warning(
                    "publish_pdf_to_discussion_failed",
                    channel=channel,
                    error=str(last_error),
                    fallback="channel_reply",
                )
                await _send_channel_with_retry(
                    lambda: bot.send_document(
                        channel,
                        FSInputFile(pdf_path),
                        reply_to_message_id=channel_message_id,
                    )
                )
                log.info("published_to_channel", channel=channel, pdf_path=pdf_path, pdf_in_discussion=False)
        else:
            await _send_channel_with_retry(
                lambda: bot.send_document(
                    channel,
                    FSInputFile(pdf_path),
                    reply_to_message_id=channel_message_id,
                )
            )
            log.info("published_to_channel", channel=channel, pdf_path=pdf_path, pdf_in_discussion=False)
    else:
        log.warning("published_text_only", channel=channel, reason="pdf_not_found", path=pdf_path)


async def publish_to_all_channels(
    bot: Bot,
    channels: list[str],
    caption: str,
    pdf_path: str,
    pdf_storage_path: str = "/data/pdfs",
    userbot_api_url: str | None = None,
    userbot_api_token: str | None = None,
) -> None:
    """
    Publish to all given channels. Pauses between channels to reduce rate limits.
    Serialized globally so only one publication runs at a time. Logs errors per channel but does not raise.
    """
    async with _publish_lock:
        for i, channel in enumerate(channels):
            ch = (channel or "").strip()
            if not ch:
                continue
            if i > 0:
                await asyncio.sleep(PUBLISH_DELAY_BETWEEN_CHANNELS)
            try:
                await publish_to_channel(
                    bot, ch, caption, pdf_path, pdf_storage_path,
                    userbot_api_url=userbot_api_url,
                    userbot_api_token=userbot_api_token,
                )
            except Exception as e:
                log.error(
                    "publish_to_channel_failed",
                    channel=ch,
                    error=str(e),
                    exc_info=True,
                )
                raise