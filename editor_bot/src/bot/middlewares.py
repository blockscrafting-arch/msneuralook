"""Middlewares: editor-only check, data injection, logging."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
import structlog

log = structlog.get_logger()


class DataInjectionMiddleware(BaseMiddleware):
    """Inject pool, editor_chat_id, target_channel_id into handler data."""

    def __init__(
        self,
        pool: Any,
        editor_chat_id: int,
        target_channel_id: str,
    ) -> None:
        self.pool = pool
        self.editor_chat_id = editor_chat_id
        self.target_channel_id = target_channel_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["pool"] = self.pool
        data["editor_chat_id"] = self.editor_chat_id
        data["target_channel_id"] = self.target_channel_id
        return await handler(event, data)


class EditorOnlyMiddleware(BaseMiddleware):
    """Allow only EDITOR_CHAT_ID to use callback buttons and review commands."""

    def __init__(self, editor_chat_id: int) -> None:
        self.editor_chat_id = editor_chat_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        if user_id is not None and user_id != self.editor_chat_id:
            log.warning("unauthorized_user", user_id=user_id, editor_chat_id=self.editor_chat_id)
            if isinstance(event, CallbackQuery):
                await event.answer("Доступ только у редактора.", show_alert=True)
            return
        return await handler(event, data)
