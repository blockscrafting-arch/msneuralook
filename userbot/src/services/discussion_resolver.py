"""Resolve discussion message id from channel post via MTProto (GetDiscussionMessage)."""

import asyncio
from typing import Tuple

import structlog
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import PeerChannel

log = structlog.get_logger()

# Retries when discussion message not yet available (Telegram may need a moment)
RESOLVE_RETRIES = (0.5, 1.0, 2.0)


async def resolve_discussion_message(
    client: TelegramClient,
    channel_id: str,
    message_id: int,
) -> Tuple[int | None, int | None]:
    """
    Get discussion group chat_id and message_id for a channel post.

    Uses GetDiscussionMessageRequest. Returns (discussion_chat_id, discussion_message_id)
    in Bot API format, or (None, None) on failure.

    Args:
        client: Connected Telethon client.
        channel_id: Channel identifier (-100... or @username).
        message_id: Message id in the channel.

    Returns:
        (discussion_chat_id, discussion_message_id) or (None, None).
    """
    channel_id = (channel_id or "").strip()
    if not channel_id or message_id is None or message_id < 1:
        return None, None

    # Telethon get_input_entity(str) ищет по username; для Bot API id "-100..." передаём int (peer id)
    try:
        peer_id_int = int(channel_id)
        entity_arg: int | str = peer_id_int if peer_id_int < 0 else channel_id
    except ValueError:
        entity_arg = channel_id  # @username

    last_error: Exception | None = None
    for attempt, delay in enumerate([0.0] + list(RESOLVE_RETRIES)):
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            peer = await client.get_input_entity(entity_arg)
            result = await client(GetDiscussionMessageRequest(peer=peer, msg_id=message_id))
        except Exception as e:
            last_error = e
            log.warning(
                "discussion_resolve_attempt",
                channel_id=channel_id,
                message_id=message_id,
                attempt=attempt + 1,
                error=str(e),
            )
            continue

        if not result.messages:
            log.warning(
                "discussion_resolve_no_messages",
                channel_id=channel_id,
                message_id=message_id,
            )
            return None, None

        msg = result.messages[0]
        peer = getattr(msg, "peer_id", None)
        if peer is None:
            return None, None
        if isinstance(peer, PeerChannel):
            # Bot API format: -100xxxxxxxxx
            discussion_chat_id = -(1000000000000 + peer.channel_id)
        else:
            chat_id = getattr(peer, "chat_id", None)
            if chat_id is None:
                return None, None
            discussion_chat_id = -chat_id if chat_id > 0 else chat_id
        discussion_message_id = msg.id
        log.info(
            "discussion_resolved",
            channel_id=channel_id,
            message_id=message_id,
            discussion_chat_id=discussion_chat_id,
            discussion_message_id=discussion_message_id,
        )
        return discussion_chat_id, discussion_message_id

    log.error(
        "discussion_resolve_failed",
        channel_id=channel_id,
        message_id=message_id,
        error=str(last_error),
    )
    return None, None
