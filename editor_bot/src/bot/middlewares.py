"""Middlewares: editor-only check, admin-only check, data injection."""

import time
from typing import Any, Awaitable, Callable, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
import structlog

from src.database.admin_repository import get_admin_user_ids, get_editor_user_ids

log = structlog.get_logger()

CACHE_TTL_SEC = 60


def _get_user_id(event: TelegramObject) -> Optional[int]:
    if isinstance(event, CallbackQuery):
        return event.from_user.id if event.from_user else None
    if isinstance(event, Message):
        return event.from_user.id if event.from_user else None
    return None


class DataInjectionMiddleware(BaseMiddleware):
    """Inject pool, target_channel_id (fallback), pdf_storage_path, super_admin_id, bot, userbot_api into handler data."""

    def __init__(
        self,
        pool: Any,
        target_channel_id: str,
        pdf_storage_path: str = "/data/pdfs",
        super_admin_id: Optional[int] = None,
        bot: Optional[Any] = None,
        userbot_api_url: Optional[str] = None,
        userbot_api_token: Optional[str] = None,
        alert_chat_id: Optional[int] = None,
    ) -> None:
        self.pool = pool
        self.target_channel_id = target_channel_id
        self.pdf_storage_path = pdf_storage_path.rstrip("/") or "/data/pdfs"
        self.super_admin_id = super_admin_id
        self.bot = bot
        self.userbot_api_url = (userbot_api_url or "").strip() or None
        self.userbot_api_token = (userbot_api_token or "").strip() or None
        self.alert_chat_id = alert_chat_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["pool"] = self.pool
        data["target_channel_id"] = self.target_channel_id
        data["pdf_storage_path"] = self.pdf_storage_path
        data["super_admin_id"] = self.super_admin_id
        if self.bot is not None:
            data["bot"] = self.bot
        data["userbot_api_url"] = self.userbot_api_url
        data["userbot_api_token"] = self.userbot_api_token
        data["alert_chat_id"] = self.alert_chat_id
        return await handler(event, data)


class EditorOnlyMiddleware(BaseMiddleware):
    """Allow only users from editors table (cached 60s). Fallback: single editor_chat_id from env if DB empty."""

    def __init__(
        self,
        pool: Any,
        fallback_editor_chat_id: Optional[int] = None,
    ) -> None:
        self.pool = pool
        self.fallback_editor_chat_id = fallback_editor_chat_id
        self._cached: set[int] = set()
        self._last_refresh: float = 0.0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = _get_user_id(event)
        if user_id is None:
            return await handler(event, data)
        if time.monotonic() - self._last_refresh > CACHE_TTL_SEC:
            self._cached = await get_editor_user_ids(self.pool)
            if not self._cached and self.fallback_editor_chat_id is not None:
                self._cached = {self.fallback_editor_chat_id}
            self._last_refresh = time.monotonic()
        if user_id not in self._cached:
            log.warning("unauthorized_editor", user_id=user_id)
            if isinstance(event, CallbackQuery):
                await event.answer("Доступ только у редактора.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("Доступ только у редактора.")
            return
        return await handler(event, data)


class AdminOnlyMiddleware(BaseMiddleware):
    """Allow only users from admins table (cached 60s). Fallback: super_admin_id from env if DB empty."""

    def __init__(
        self,
        pool: Any,
        super_admin_id: Optional[int] = None,
    ) -> None:
        self.pool = pool
        self.super_admin_id = super_admin_id
        self._cached: set[int] = set()
        self._last_refresh: float = 0.0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = _get_user_id(event)
        if user_id is None:
            return await handler(event, data)
        if time.monotonic() - self._last_refresh > CACHE_TTL_SEC:
            self._cached = await get_admin_user_ids(self.pool)
            if not self._cached and self.super_admin_id is not None:
                self._cached = {self.super_admin_id}
            self._last_refresh = time.monotonic()
        if user_id not in self._cached:
            log.warning("unauthorized_admin", user_id=user_id)
            if isinstance(event, CallbackQuery):
                await event.answer("Доступ только у админа.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("Доступ только у админа.")
            return
        return await handler(event, data)


class AdminPanelMiddleware(BaseMiddleware):
    """Allow editors and admins into admin panel. For callbacks admin_ed* and admin_adm* only admins pass."""

    def __init__(
        self,
        pool: Any,
        super_admin_id: Optional[int] = None,
    ) -> None:
        self.pool = pool
        self.super_admin_id = super_admin_id
        self._editor_ids: set[int] = set()
        self._admin_ids: set[int] = set()
        self._last_refresh: float = 0.0

    async def _refresh_cache(self) -> None:
        if time.monotonic() - self._last_refresh <= CACHE_TTL_SEC:
            return
        self._editor_ids = await get_editor_user_ids(self.pool)
        self._admin_ids = await get_admin_user_ids(self.pool)
        if not self._admin_ids and self.super_admin_id is not None:
            self._admin_ids = {self.super_admin_id}
        self._last_refresh = time.monotonic()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = _get_user_id(event)
        if user_id is None:
            return await handler(event, data)
        await self._refresh_cache()
        if isinstance(event, CallbackQuery) and event.data:
            data_str = event.data
            if data_str.startswith("admin_ed") or data_str.startswith("admin_adm"):
                if user_id not in self._admin_ids:
                    await event.answer("Доступ только у администраторов.", show_alert=True)
                    return
        if user_id not in self._editor_ids and user_id not in self._admin_ids:
            log.warning("unauthorized_admin_panel", user_id=user_id)
            if isinstance(event, CallbackQuery):
                await event.answer("Доступ только у редактора или админа.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("Доступ только у редактора или админа.")
            return
        return await handler(event, data)
