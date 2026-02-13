"""Telethon client setup. Uses opentele when available (TDesktop-like API), fallback to plain Telethon."""

from typing import Optional, Union

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


def _parse_proxy_url(proxy_url: str):
    """
    Parse proxy URL (http:// or socks5://) into tuple for Telethon/python-socks.
    Returns (proxy_type, host, port) or (proxy_type, host, port, rdns, username, password).
    """
    from python_socks import parse_proxy_url as _parse

    proxy_type, host, port, username, password = _parse(proxy_url)
    if not (host and str(host).strip()):
        raise ValueError("proxy URL has no host")
    port = int(port) if port is not None else (1080 if "socks" in str(proxy_type).lower() else 3128)
    if username and password:
        return (proxy_type, host, port, True, username, password)
    return (proxy_type, host, port)


def create_client(
    api_id: int,
    api_hash: str,
    session_string: str,
    proxy: Optional[Union[tuple, str]] = None,
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
        proxy: Optional. Proxy URL (e.g. http://proxy:3128) or tuple for Telethon; if URL, parsed via python_socks.

    Returns:
        TelegramClient instance (not connected yet).
    """
    session = StringSession(session_string)
    proxy_tuple = _parse_proxy_url(proxy) if isinstance(proxy, str) else proxy
    kwargs = {"proxy": proxy_tuple} if proxy_tuple is not None else {}
    if _OPENTELE_AVAILABLE:
        try:
            api = APIData(api_id=api_id, api_hash=api_hash)
            api = api.Generate(unique_id="parser_userbot")
            client = OpenTeleClient(session=session, api=api, **kwargs)
            log.info("client_created", backend="opentele", proxy=bool(kwargs))
            return client
        except TypeError:
            # OpenTeleClient may not support proxy
            client = OpenTeleClient(session=session, api=api)
            log.info("client_created", backend="opentele", proxy=False)
            return client
        except Exception as e:
            log.warning("opentele_client_failed", error=str(e), fallback="telethon")
    client = TelegramClient(
        session=session,
        api_id=api_id,
        api_hash=api_hash,
        **kwargs,
    )
    log.info("client_created", backend="telethon", proxy=bool(kwargs))
    return client
