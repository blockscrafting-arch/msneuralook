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
    original_text: Optional[str]
    pdf_path: str
    extracted_text: Optional[str]
    summary: Optional[str]
    edited_summary: Optional[str]
    editor_message_id: Optional[int]
    status: str
    created_at: datetime
    updated_at: datetime

    def display_summary(self) -> str:
        """Text to show to editor (edited if set, else summary)."""
        return (self.edited_summary or self.summary) or ""
