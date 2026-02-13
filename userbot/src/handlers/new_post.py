"""Handler for new channel posts: PDF, text, or both. Monitored channels from DB (cached 30s)."""

import time

import asyncpg
from telethon import events
import structlog

from src.database.source_channels import get_active_channel_identifiers, get_keywords
from src.database.outbox import insert_outbox
from src.services.pdf_downloader import download_pdf_to_storage, get_pdf_document

log = structlog.get_logger()

CACHE_TTL_SEC = 30
_monitored_cache: set[str] = set()
_monitored_last_refresh: float = 0.0
_keywords_cache: list[str] = []
_keywords_last_refresh: float = 0.0


def get_channel_identifier(message) -> str:
    """Extract channel id (numeric string) or empty for logging and payload."""
    peer = getattr(message, "peer_id", None)
    if peer is None:
        return ""
    channel_id = getattr(peer, "channel_id", None)
    if channel_id is not None:
        return str(channel_id)
    chat_id = getattr(peer, "chat_id", None)
    if chat_id is not None:
        return str(chat_id)
    return ""


def _build_monitored_set(identifiers: list[str]) -> set[str]:
    """Build set for fast lookup: include -100... and numeric part (for peer.channel_id), @username as-is."""
    out: set[str] = set()
    for ident in identifiers:
        ident = (ident or "").strip()
        if not ident:
            continue
        out.add(ident)
        if ident.startswith("-100"):
            out.add(ident[4:])  # numeric part for Telethon peer.channel_id
        elif ident.startswith("-"):
            out.add(ident.lstrip("-"))
    return out


async def _get_monitored(pool: asyncpg.Pool, fallback_source: str) -> set[str]:
    """Return set of monitored channel identifiers (cached CACHE_TTL_SEC)."""
    global _monitored_cache, _monitored_last_refresh
    now = time.monotonic()
    if now - _monitored_last_refresh > CACHE_TTL_SEC:
        identifiers = await get_active_channel_identifiers(pool)
        if not identifiers and fallback_source:
            identifiers = [fallback_source]
        _monitored_cache = _build_monitored_set(identifiers)
        _monitored_last_refresh = now
    return _monitored_cache


async def _get_keywords(pool: asyncpg.Pool) -> list[str]:
    """Return list of keyword words (cached CACHE_TTL_SEC). Empty = no filter."""
    global _keywords_cache, _keywords_last_refresh
    now = time.monotonic()
    if now - _keywords_last_refresh > CACHE_TTL_SEC:
        _keywords_cache = await get_keywords(pool)
        _keywords_last_refresh = now
    return _keywords_cache


def _is_message_from_monitored(channel_id_str: str, monitored: set[str]) -> bool:
    """True if channel_id_str matches any monitored identifier."""
    if channel_id_str in monitored:
        return True
    full_id = f"-100{channel_id_str}" if channel_id_str.isdigit() else ""
    if full_id and full_id in monitored:
        return True
    return False


def register_new_post_handler(client, config, pool: asyncpg.Pool) -> None:
    """
    Register handler for new messages in monitored channels: PDF, text, or both.

    Monitored channels are read from DB (source_channels), refreshed every 30s.
    If DB has no channels, SOURCE_CHANNEL from config is used as fallback.

    Args:
        client: Telethon TelegramClient (connected).
        config: Settings with N8N_WEBHOOK_URL, PDF_STORAGE_PATH, get_source_channel_fallback().
        pool: asyncpg pool to read source_channels.
    """
    fallback_source = config.get_source_channel_fallback()

    @client.on(events.NewMessage())
    async def on_new_message(event: events.NewMessage.Event) -> None:
        message = event.message
        channel_id_str = get_channel_identifier(message)
        if not channel_id_str:
            return
        monitored = await _get_monitored(pool, fallback_source)
        if not monitored:
            log.warning(
                "skip_no_monitored_channels",
                message_id=message.id,
                channel_id=channel_id_str,
                fallback=fallback_source or "(none)",
            )
            return
        if not _is_message_from_monitored(channel_id_str, monitored):
            log.info(
                "skip_channel_not_monitored",
                message_id=message.id,
                channel_id=channel_id_str,
                monitored_count=len(monitored),
            )
            return

        has_pdf = get_pdf_document(message)
        post_text = message.text or ""

        if not has_pdf and not post_text:
            log.info(
                "skip_empty_post",
                message_id=message.id,
                channel_id=channel_id_str,
                has_media=bool(message.media),
            )
            return  # пустой пост — пропустить

        keywords = await _get_keywords(pool)
        if keywords:
            text_lower = post_text.lower()
            if not any(kw in text_lower for kw in keywords):
                log.info(
                    "skip_no_keyword_match",
                    message_id=message.id,
                    channel_id=channel_id_str,
                    keyword_count=len(keywords),
                )
                return  # нет совпадений по маркерам — пропустить

        pdf_path = ""
        pdf_missing = False
        if has_pdf:
            pdf_path = await download_pdf_to_storage(
                client,
                message,
                config.PDF_STORAGE_PATH,
            )
            if not pdf_path:
                pdf_missing = True
                log.warning("pdf_download_failed_using_outbox", message_id=message.id)

        log.info(
            "new_post",
            message_id=message.id,
            peer=channel_id_str,
            has_pdf=bool(pdf_path),
            pdf_missing=pdf_missing,
        )
        outbox_id = await insert_outbox(
            pool,
            channel_id=channel_id_str,
            message_id=message.id,
            pdf_path=pdf_path,
            pdf_missing=pdf_missing,
            post_text=post_text,
            source_channel=channel_id_str,
        )
        if outbox_id is None:
            log.debug("outbox_duplicate_skipped", message_id=message.id, channel_id=channel_id_str)
