"""Tests for post handlers."""

import pytest
from unittest.mock import MagicMock

from src.services.pdf_downloader import get_pdf_document


def test_get_pdf_document_no_media() -> None:
    """If message has no media, returns None."""
    msg = MagicMock()
    msg.media = None
    assert get_pdf_document(msg) is None


def test_get_pdf_document_not_document() -> None:
    """If media is not a document, returns None."""
    msg = MagicMock()
    msg.media = MagicMock()
    msg.media.document = None
    assert get_pdf_document(msg) is None
