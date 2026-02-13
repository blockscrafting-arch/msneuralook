"""Dataclasses for Post and config rows."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Post:
    """One row from posts table."""

    id: int
    source_channel: str
    source_message_id: int
    pdf_path: str
    original_text: Optional[str] = None
    extracted_text: Optional[str] = None
    summary: Optional[str] = None
    edited_summary: Optional[str] = None
    editor_message_id: Optional[int] = None
    status: str = "processing"
    scheduled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    delivery_attempts: int = 0
    last_delivery_error: Optional[str] = None
    next_retry_at: Optional[datetime] = None

    def display_summary(self) -> str:
        """Text to show to editor (edited if set, else summary)."""
        return (self.edited_summary or self.summary) or ""
