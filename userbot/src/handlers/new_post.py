"""Handler for new channel posts containing PDF."""

from telethon import events
import structlog

from src.services.pdf_downloader import download_pdf_to_storage, get_pdf_document
from src.services.webhook_sender import send_to_n8n_webhook

log = structlog.get_logger()


def get_channel_identifier(message) -> str:
    """Extract channel id or username for logging and payload."""
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


def register_new_post_handler(client, config) -> None:
    """
    Register handler for new messages in SOURCE_CHANNEL that contain a PDF.

    On such messages: download PDF to storage, then POST to n8n webhook.

    Args:
        client: Telethon TelegramClient (connected).
        config: Settings object with N8N_WEBHOOK_URL, SOURCE_CHANNEL, PDF_STORAGE_PATH.
    """
    source = config.get_source_channel_id_or_username()
    if not source:
        log.warning("SOURCE_CHANNEL is empty; handler will not filter by channel")

    @client.on(events.NewMessage(chats=source if source else None))
    async def on_new_message(event: events.NewMessage.Event) -> None:
        message = event.message
        if not get_pdf_document(message):
            return
        log.info("new_pdf_post", message_id=message.id, peer=get_channel_identifier(message))

        pdf_path = await download_pdf_to_storage(
            client,
            message,
            config.PDF_STORAGE_PATH,
        )
        if not pdf_path:
            log.error("skip_webhook_no_pdf", message_id=message.id)
            return

        post_text = message.text or ""
        channel_id = get_channel_identifier(message) or source
        ok = await send_to_n8n_webhook(
            config.N8N_WEBHOOK_URL,
            post_text=post_text,
            pdf_path=pdf_path,
            message_id=message.id,
            channel_id=channel_id,
            source_channel=source or channel_id,
        )
        if not ok:
            log.error("webhook_not_acked", message_id=message.id)
