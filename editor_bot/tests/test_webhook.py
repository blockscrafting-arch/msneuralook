"""Tests for n8n webhook receiver."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from src.database.models import Post
from src.webhook import n8n_receiver
from src.webhook.n8n_receiver import (
    handle_incoming_post,
    _send_to_editors_background,
    _send_to_one_editor,
    POST_ID_MAX,
)


WEBHOOK_TOKEN = "test-webhook-token"


def _request_with_auth(app_overrides=None):
    """Request with valid Bearer token so handler runs (auth required when token set)."""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer test-webhook-token"}
    request.app = {"webhook_token": WEBHOOK_TOKEN, **(app_overrides or {})}
    return request


@pytest.mark.asyncio
async def test_handle_incoming_post_unauthorized_when_token_empty() -> None:
    """When webhook token is empty, any request gets 403."""
    request = MagicMock()
    request.headers = {}
    request.app = {"pool": MagicMock(), "bot": MagicMock(), "webhook_token": ""}
    request.json = AsyncMock(return_value={"post_id": 1})
    with patch("src.webhook.n8n_receiver.get_editors_list", new_callable=AsyncMock, return_value=[{"user_id": 1}]):
        resp = await handle_incoming_post(request)
    assert resp.status == 403


@pytest.mark.asyncio
async def test_handle_incoming_post_unauthorized_when_token_wrong() -> None:
    """When Authorization Bearer does not match webhook token, returns 403."""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer wrong-token"}
    request.app = {"pool": MagicMock(), "bot": MagicMock(), "webhook_token": "right-token"}
    request.json = AsyncMock(return_value={"post_id": 1})
    resp = await handle_incoming_post(request)
    assert resp.status == 403


@pytest.mark.asyncio
async def test_handle_incoming_post_post_id_too_large_returns_400() -> None:
    """When post_id exceeds POST_ID_MAX, returns 400."""
    request = _request_with_auth({"pool": MagicMock(), "bot": MagicMock()})
    request.json = AsyncMock(return_value={"post_id": POST_ID_MAX + 1})
    resp = await handle_incoming_post(request)
    assert resp.status == 400
    body = json.loads(resp.body.decode()) if isinstance(resp.body, bytes) else resp.body
    assert "post_id" in (body.get("error") or "").lower() or "large" in (body.get("error") or "").lower()


@pytest.mark.asyncio
async def test_handle_incoming_post_missing_post_id() -> None:
    """When post_id is missing, returns 400."""
    request = _request_with_auth()
    request.json = AsyncMock(return_value={"summary": "x"})
    resp = await handle_incoming_post(request)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_handle_incoming_post_invalid_json() -> None:
    """When body is not JSON, returns 400."""
    request = _request_with_auth()
    request.json = AsyncMock(side_effect=ValueError("bad"))
    resp = await handle_incoming_post(request)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_handle_incoming_post_no_editors_returns_503() -> None:
    """When no editors in DB, returns 503."""
    request = _request_with_auth({"pool": MagicMock(), "bot": MagicMock()})
    request.json = AsyncMock(return_value={"post_id": 1})
    with patch("src.webhook.n8n_receiver.get_editors_list", new_callable=AsyncMock, return_value=[]):
        resp = await handle_incoming_post(request)
    assert resp.status == 503


@pytest.mark.asyncio
async def test_handle_incoming_post_already_sent_returns_200_no_resend() -> None:
    """When post is already pending_review (or has editor_message_id), return 200 with already_sent and do not send to editors."""
    post = Post(
        id=10,
        source_channel="-1001",
        source_message_id=5,
        pdf_path="",
        status="pending_review",
        editor_message_id=999,
    )
    request = _request_with_auth({"pool": MagicMock(), "bot": MagicMock(), "pdf_storage_path": "/data/pdfs"})
    request.json = AsyncMock(return_value={"post_id": 10, "summary": "x", "pdf_path": ""})
    bot = request.app["bot"]
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    with patch("src.webhook.n8n_receiver.get_editors_list", new_callable=AsyncMock, return_value=[{"user_id": 123}]):
        with patch("src.webhook.n8n_receiver.get_post_by_id", new_callable=AsyncMock, return_value=post):
            resp = await handle_incoming_post(request)
    assert resp.status == 200
    body = json.loads(resp.body.decode()) if isinstance(resp.body, bytes) else resp.body
    assert body.get("ok") is True
    assert body.get("already_sent") is True
    assert body.get("post_id") == 10
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_handle_incoming_post_summary_asterisks_stripped() -> None:
    """Summary has ** and * stripped before sending to editors; no raw asterisks in message."""
    post = Post(
        id=11,
        source_channel="-1002",
        source_message_id=6,
        pdf_path="",
        status="processing",
        editor_message_id=None,
    )
    request = _request_with_auth({"pool": MagicMock(), "bot": MagicMock(), "pdf_storage_path": "/data/pdfs"})
    request.json = AsyncMock(
        return_value={
            "post_id": 11,
            "summary": "**bold** and *italic* here",
            "pdf_path": "",
        }
    )
    bot = request.app["bot"]
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    created_tasks = []

    def capture_task(coro):
        t = asyncio.ensure_future(coro)
        created_tasks.append(t)
        return t

    with patch("src.webhook.n8n_receiver.get_editors_list", new_callable=AsyncMock, return_value=[{"user_id": 456}]):
        with patch("src.webhook.n8n_receiver.get_post_by_id", new_callable=AsyncMock, return_value=post):
            with patch("src.webhook.n8n_receiver.update_post_status", new_callable=AsyncMock):
                with patch("src.webhook.n8n_receiver.add_audit_log", new_callable=AsyncMock):
                    with patch("src.webhook.n8n_receiver.asyncio.create_task", side_effect=capture_task):
                        resp = await handle_incoming_post(request)
                        if created_tasks:
                            await created_tasks[0]
    if created_tasks:
        await created_tasks[0]
    assert resp.status == 200
    assert bot.send_message.called
    sent_text = bot.send_message.call_args[0][1]
    assert "*" not in sent_text
    assert "bold" in sent_text and "italic" in sent_text


@pytest.mark.asyncio
async def test_send_to_editors_background_pdf_file_missing_send_document_not_called(capsys) -> None:
    """When pdf_path is set but os.path.isfile returns False, send_document is not called; warning is logged (structlog to stdout)."""
    post = Post(
        id=20,
        source_channel="-100",
        source_message_id=1,
        pdf_path="/data/pdfs/missing.pdf",
        status="processing",
        editor_message_id=None,
    )
    pool = MagicMock()
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    bot.send_document = AsyncMock()
    pdf_path = "/data/pdfs/missing.pdf"
    pdf_storage_path = "/data/pdfs"
    recipient_ids = [111]

    with patch("src.webhook.n8n_receiver.get_post_by_id", new_callable=AsyncMock, return_value=post):
        with patch("src.webhook.n8n_receiver.update_post_status", new_callable=AsyncMock):
            with patch("src.webhook.n8n_receiver.add_audit_log", new_callable=AsyncMock):
                with patch("src.webhook.n8n_receiver.os.path.isfile", return_value=False):
                    await _send_to_editors_background(
                        pool, bot, 20, "Summary", pdf_path, pdf_storage_path, recipient_ids
                    )

    bot.send_document.assert_not_called()
    out = capsys.readouterr().out
    assert "incoming_post_pdf_file_missing" in out and "file_not_found" in out


@pytest.mark.asyncio
async def test_send_to_one_editor_timeout_returns_none_and_logs_warning(capsys) -> None:
    """When asyncio.wait_for raises TimeoutError twice (no retry success), returns None and logs warning with timeout_seconds."""
    bot = MagicMock()
    chunks = ["Part one"]
    kb = MagicMock()
    post_id = 1
    pdf_path = ""
    use_pdf_file = False

    async def raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch("src.webhook.n8n_receiver.asyncio.wait_for", side_effect=raise_timeout), patch(
        "src.webhook.n8n_receiver.asyncio.sleep", new_callable=AsyncMock
    ):
        result = await _send_to_one_editor(bot, 999, chunks, kb, post_id, pdf_path, use_pdf_file)

    assert result is None
    out = capsys.readouterr().out
    assert "incoming_post_send_to_editor_failed" in out and "timeout_seconds" in out


@pytest.mark.asyncio
async def test_send_to_one_editor_pdf_timeout_returns_first_message_id_no_pdf(capsys) -> None:
    """Text sent once; PDF attempt 1 TimeoutError, retry attempt 2 TimeoutError; returns first_message_id, had_pdf false, logs retry and pdf_send_failed."""
    bot = MagicMock()
    chunks = ["Part one"]
    kb = MagicMock()
    post_id = 1
    pdf_path = "/data/pdfs/file.pdf"
    use_pdf_file = True
    msg_ok = MagicMock(message_id=123)

    with patch(
        "src.webhook.n8n_receiver.asyncio.wait_for",
        side_effect=[msg_ok, asyncio.TimeoutError(), asyncio.TimeoutError()],
    ):
        result = await _send_to_one_editor(bot, 999, chunks, kb, post_id, pdf_path, use_pdf_file)

    assert result == 123
    out = capsys.readouterr().out
    assert "incoming_post_pdf_retry" in out
    assert "incoming_post_pdf_send_failed" in out
    assert "incoming_post_sent_to_editor" in out
    assert "had_pdf" in out


@pytest.mark.asyncio
async def test_send_to_one_editor_text_sent_once_pdf_two_attempts_both_timeout(capsys) -> None:
    """send_message called once; PDF first attempt TimeoutError, retry second attempt TimeoutError; no duplicate text."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    bot.send_document = AsyncMock(side_effect=asyncio.TimeoutError())
    chunks = ["Only one part"]
    kb = MagicMock()
    post_id = 2
    pdf_path = "/data/pdfs/two.pdf"
    use_pdf_file = True

    result = await _send_to_one_editor(bot, 100, chunks, kb, post_id, pdf_path, use_pdf_file)

    assert result == 1
    assert bot.send_message.call_count == 1
    assert bot.send_document.call_count == 2


@pytest.mark.asyncio
async def test_send_to_one_editor_pdf_retry_succeeds(capsys) -> None:
    """First PDF attempt TimeoutError, retry succeeds; send_document called twice, had_pdf true, log has retry."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    bot.send_document = AsyncMock(side_effect=[asyncio.TimeoutError(), MagicMock()])
    chunks = ["One part"]
    kb = MagicMock()
    post_id = 3
    pdf_path = "/data/pdfs/three.pdf"
    use_pdf_file = True

    result = await _send_to_one_editor(bot, 100, chunks, kb, post_id, pdf_path, use_pdf_file)

    assert result == 1
    assert bot.send_document.call_count == 2
    out = capsys.readouterr().out
    assert "incoming_post_pdf_retry" in out
    assert "incoming_post_sent_to_editor" in out
    assert "had_pdf" in out and ("True" in out or "true" in out.lower())


@pytest.mark.asyncio
async def test_send_to_one_editor_pdf_request_timeout_error_retry_succeeds(capsys) -> None:
    """First PDF attempt raises Exception with 'Request timeout error' text (e.g. TelegramNetworkError); retry succeeds."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    bot.send_document = AsyncMock(
        side_effect=[
            Exception("HTTP Client says - Request timeout error"),
            MagicMock(),
        ],
    )
    chunks = ["One part"]
    kb = MagicMock()
    post_id = 4
    pdf_path = "/data/pdfs/four.pdf"
    use_pdf_file = True

    result = await _send_to_one_editor(bot, 100, chunks, kb, post_id, pdf_path, use_pdf_file)

    assert result == 1
    assert bot.send_document.call_count == 2
    out = capsys.readouterr().out
    assert "incoming_post_pdf_retry" in out
    assert "incoming_post_sent_to_editor" in out
    assert "had_pdf" in out and ("True" in out or "true" in out.lower())


@pytest.mark.asyncio
async def test_send_to_editors_background_discards_post_id_on_early_return() -> None:
    """При раннем выходе (post not found, duplicate skip) post_id снимается с _post_ids_sending."""
    post = Post(
        id=404,
        source_channel="-100",
        source_message_id=1,
        pdf_path="",
        status="pending_review",  # не processing/send_failed — будет duplicate_skipped
        editor_message_id=111,
    )
    pool = MagicMock()
    bot = MagicMock()
    with patch("src.webhook.n8n_receiver.get_post_by_id", new_callable=AsyncMock, return_value=post):
        await _send_to_editors_background(
            pool, bot, 404, "Summary", "", "/data/pdfs", [111]
        )
    assert 404 not in n8n_receiver._post_ids_sending


@pytest.mark.asyncio
async def test_send_to_editors_background_two_editors_first_success_uses_first_message_id() -> None:
    """When two editors, first returns message_id and second None, status is updated with first editor's message_id."""
    post = Post(
        id=30,
        source_channel="-100",
        source_message_id=2,
        pdf_path="",
        status="processing",
        editor_message_id=None,
    )
    pool = MagicMock()
    bot = MagicMock()
    recipient_ids = [100, 200]

    with patch("src.webhook.n8n_receiver.get_post_by_id", new_callable=AsyncMock, return_value=post):
        with patch("src.webhook.n8n_receiver._send_to_one_editor", new_callable=AsyncMock, side_effect=[123, None]):
            with patch("src.webhook.n8n_receiver.update_post_status", new_callable=AsyncMock) as upd:
                with patch("src.webhook.n8n_receiver.add_audit_log", new_callable=AsyncMock):
                    await _send_to_editors_background(
                        pool, bot, 30, "Summary", "", "/data/pdfs", recipient_ids
                    )

    upd.assert_called_once()
    # update_post_status(pool, post_id, status, ..., editor_message_id=...)
    assert upd.call_args[0][2] == "pending_review"
    assert upd.call_args[1].get("editor_message_id") == 123
    # После завершения (успех или любой выход) post_id должен быть снят с «в отправке»
    assert 30 not in n8n_receiver._post_ids_sending
