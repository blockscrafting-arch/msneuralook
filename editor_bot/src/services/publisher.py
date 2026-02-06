"""Publish approved post to target Telegram channel."""

import os
from typing import Optional

from aiogram import Bot
from aiogram.types import FSInputFile
import structlog

log = structlog.get_logger()


async def publish_to_channel(
    bot: Bot,
    target_channel_id: str,
    caption: str,
    pdf_path: str,
) -> None:
    """
    Send caption (summary) and PDF to the target channel.

    Args:
        bot: Aiogram Bot instance.
        target_channel_id: Telegram channel ID (e.g. -1001234567890).
        caption: Text to publish (summary).
        pdf_path: Full path to PDF file on disk.

    Raises:
        Exception: On Telegram API or file errors.
    """
    channel = target_channel_id.strip()
    if not channel:
        raise ValueError("TARGET_CHANNEL_ID is empty")
    if os.path.isfile(pdf_path):
        doc = FSInputFile(pdf_path)
        await bot.send_document(
            channel,
            doc,
            caption=caption[:1024],
        )
        log.info("published_to_channel", channel=channel, pdf_path=pdf_path)
    else:
        await bot.send_message(channel, caption)
        log.warning("published_text_only", channel=channel, reason="pdf_not_found", path=pdf_path)
