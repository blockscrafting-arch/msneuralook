"""Telethon client setup. Uses opentele when available (TDesktop-like API), fallback to plain Telethon."""

from telethon.sessions import StringSession
from telethon import TelegramClient

import structlog

log = structlog.get_logger()

try:
    from opentele.tl import TelegramClient as OpenTeleClient
    from opentele.api import APIData
    _OPENTELE_AVAILABLE = True
except ImportError:
    _OPENTELE_AVAILABLE = False


def create_client(
    api_id: int,
    api_hash: str,
    session_string: str,
):
    """
    Create and return a Telegram client (opentele if available, else Telethon).

    With opentele: uses APIData with your api_id/api_hash and randomized device
    params (TDesktop-like), which can reduce ban risk. Falls back to standard
    Telethon if opentele is not installed.

    Args:
        api_id: Telegram API ID from my.telegram.org.
        api_hash: Telegram API hash.
        session_string: Session serialized with StringSession.

    Returns:
        TelegramClient instance (not connected yet).
    """
    session = StringSession(session_string)
    if _OPENTELE_AVAILABLE:
        try:
            api = APIData(api_id=api_id, api_hash=api_hash)
            api = api.Generate(unique_id="parser_userbot")
            client = OpenTeleClient(session=session, api=api)
            log.info("client_created", backend="opentele")
            return client
        except Exception as e:
            log.warning("opentele_client_failed", error=str(e), fallback="telethon")
    client = TelegramClient(
        session=session,
        api_id=api_id,
        api_hash=api_hash,
    )
    return client
