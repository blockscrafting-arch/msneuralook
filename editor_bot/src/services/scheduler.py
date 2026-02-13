"""Background scheduler: publish posts with status=scheduled when scheduled_at <= NOW()."""

import asyncio
from typing import Any

from aiogram import Bot
import structlog

from src.database.admin_repository import get_channel_ids_for_publish, get_config_value, get_editors_list
from src.database.repository import (
    add_audit_log,
    get_posts_for_delivery_retry,
    get_scheduled_posts_due,
    reset_stuck_publishing_posts,
    reset_send_failed_for_retry,
    update_post_status,
)
from src.services.publisher import publish_to_all_channels
from src.webhook.n8n_receiver import _send_to_editors_background

log = structlog.get_logger()


async def run_scheduler(
    pool: Any,
    bot: Bot,
    pdf_storage_path: str = "/data/pdfs",
    interval: int = 30,
    userbot_api_url: str | None = None,
    userbot_api_token: str | None = None,
    alert_chat_id: int | None = None,
) -> None:
    """
    Loop: every `interval` seconds fetch scheduled posts due now, publish to all target
    channels, set status to published, audit_log. Runs until cancelled.
    """
    while True:
        try:
            stuck = await reset_stuck_publishing_posts(pool)
            if stuck:
                log.warning("publishing_stuck_reset", count=stuck, msg="Posts returned to pending_review for retry")
            send_failed_reset = await reset_send_failed_for_retry(pool)
            if send_failed_reset:
                log.info("send_failed_retry_reset", count=send_failed_reset, msg="Posts re-queued for delivery to editors")
            posts = await get_scheduled_posts_due(pool)
            fallback_channel = await get_config_value(pool, "target_channel") or None
            if fallback_channel:
                fallback_channel = fallback_channel.strip() or None
            posts_retry = await get_posts_for_delivery_retry(pool, limit=25)
            editors = await get_editors_list(pool)
            recipient_ids = [e["user_id"] for e in editors] if editors else []
            for post in posts_retry:
                if recipient_ids:
                    await _send_to_editors_background(
                        pool,
                        bot,
                        post.id,
                        post.summary or "",
                        post.pdf_path or "",
                        pdf_storage_path,
                        recipient_ids,
                        alert_chat_id=alert_chat_id,
                    )
            for post in posts:
                text_for_routing = (post.original_text or "") + " " + (post.display_summary() or "")
                channel_ids = await get_channel_ids_for_publish(
                    pool, text_for_routing, fallback_channel_from_config=fallback_channel
                )
                if not channel_ids:
                    log.warning("scheduler_no_target_channels", post_id=post.id, msg="No target channels for post, skipping")
                    continue
                try:
                    text = post.display_summary()
                    await publish_to_all_channels(
                        bot,
                        channel_ids,
                        text,
                        post.pdf_path or "",
                        pdf_storage_path,
                        userbot_api_url=userbot_api_url,
                        userbot_api_token=userbot_api_token,
                    )
                    await update_post_status(pool, post.id, "published")
                    await add_audit_log(
                        pool,
                        post.id,
                        "scheduled_published",
                        actor="scheduler",
                        details={"scheduled_at": str(post.scheduled_at)},
                    )
                    log.info("scheduler_published", post_id=post.id)
                except Exception as e:
                    log.error(
                        "scheduler_publish_failed",
                        post_id=post.id,
                        error=str(e),
                        exc_info=True,
                    )
                    await add_audit_log(
                        pool,
                        post.id,
                        "scheduled_publish_failed",
                        actor="scheduler",
                        details={"scheduled_at": str(post.scheduled_at), "error": str(e)},
                    )
                    # Leave status as scheduled so next tick can retry
        except asyncio.CancelledError:
            log.info("scheduler_stopped")
            raise
        except Exception as e:
            log.error("scheduler_tick_error", error=str(e), exc_info=True)
        await asyncio.sleep(interval)
