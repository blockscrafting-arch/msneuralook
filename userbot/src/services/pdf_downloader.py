"""Download PDF from Telegram to local storage."""

from pathlib import Path

import structlog
from telethon.tl.types import Message, Document, DocumentAttributeFilename

log = structlog.get_logger()

# MIME type for PDF
PDF_MIME = "application/pdf"


def get_pdf_document(message: Message) -> Document | None:
    """
    Return the first PDF document attached to the message, if any.

    Args:
        message: Telethon Message object.

    Returns:
        Document if message has a PDF attachment, else None.
    """
    if not message.media:
        return None
    doc = None
    if hasattr(message.media, "document"):
        doc = message.media.document
    if not isinstance(doc, Document):
        return None
    for attr in doc.attributes or []:
        if isinstance(attr, DocumentAttributeFilename) and attr.file_name:
            if attr.file_name.lower().endswith(".pdf"):
                return doc
    # Fallback: check mime type if available (some clients set it)
    if getattr(doc, "mime_type", None) == PDF_MIME:
        return doc
    return None


async def download_pdf_to_storage(
    client: "telethon.client.telegramclient.TelegramClient",
    message: Message,
    storage_path: str,
) -> str | None:
    """
    Download the PDF from the message to storage_path and return the file path.

    Args:
        client: Telethon client (used to download file).
        message: Message that contains the PDF.
        storage_path: Directory path to save the file (must exist and be writable).

    Returns:
        Full path to the saved file (str), or None if no PDF or download failed.
    """
    doc = get_pdf_document(message)
    if not doc:
        return None

    base_dir = Path(storage_path)
    base_dir.mkdir(parents=True, exist_ok=True)

    # Unique filename: channel_message_id.pdf
    chat_id = getattr(message.peer_id, "channel_id", None) or getattr(
        message.peer_id, "chat_id", None
    )
    if chat_id is None:
        chat_id = 0
    safe_name = f"{chat_id}_{message.id}.pdf"
    file_path = base_dir / safe_name

    try:
        await client.download_media(message.media, file=str(file_path))
        if file_path.is_file():
            log.info("pdf_downloaded", path=str(file_path), message_id=message.id)
            return str(file_path)
    except Exception as e:
        log.error(
            "pdf_download_failed",
            message_id=message.id,
            exc_info=True,
            error=str(e),
        )
    return None
