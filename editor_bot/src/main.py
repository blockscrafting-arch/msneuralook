"""Entry point: aiogram bot (polling) + aiohttp webhook server for n8n."""

import asyncio
import os
import sys
from urllib.parse import urlparse

import aiohttp.web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import Settings
from src.utils.logging import configure_logging
from src.database.connection import create_pool_with_retry, close_pool
from src.database.admin_repository import bootstrap_admin_editor, get_config_value, set_config_value
from src.bot.handlers import admin, commands, review
from src.bot.middlewares import AdminPanelMiddleware, DataInjectionMiddleware, EditorOnlyMiddleware
from src.services.scheduler import run_scheduler
from src.utils.alert import send_alert
from src.webhook.n8n_receiver import create_app

import structlog


def main() -> None:
    """Run editor bot: start aiohttp server for n8n, then run bot with polling."""
    configure_logging()
    log = structlog.get_logger()
    try:
        config = Settings()
    except Exception as e:
        log.error("config_load_failed", error=str(e), exc_info=True)
        sys.exit(1)
    if not config.BOT_TOKEN or not config.DATABASE_URL:
        log.error("missing_config", msg="Set BOT_TOKEN and DATABASE_URL in .env")
        sys.exit(1)

    async def run() -> None:
        loop = asyncio.get_running_loop()
        pool = await create_pool_with_retry(config.DATABASE_URL)
        # Bootstrap: ensure EDITOR_CHAT_ID is in admins+editors; set target_channel if empty
        if config.EDITOR_CHAT_ID is not None:
            await bootstrap_admin_editor(pool, config.EDITOR_CHAT_ID)
            current_target = await get_config_value(pool, "target_channel")
            if (not current_target or not current_target.strip()) and config.TARGET_CHANNEL_ID:
                await set_config_value(
                    pool, "target_channel", config.TARGET_CHANNEL_ID,
                    description="ID целевого канала для публикации",
                )
        proxy_url = (config.TELEGRAM_PROXY or os.environ.get("HTTP_PROXY") or "").strip()
        if proxy_url:
            session = AiohttpSession(timeout=180, proxy=proxy_url)
            try:
                p = urlparse(proxy_url)
                safe_proxy = f"{p.scheme}://{p.hostname or ''}:{p.port or ''}"
            except Exception:
                safe_proxy = "(proxy set)"
            log.info("telegram_proxy_enabled", proxy=safe_proxy)
        else:
            session = AiohttpSession(timeout=180)
        bot = Bot(
            token=config.BOT_TOKEN,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        alert_chat_id = config.ALERT_CHAT_ID

        def _asyncio_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
            exc = context.get("exception")
            msg = context.get("message", "")
            exc_str = str(exc) if exc else ""
            is_connection_error = (
                exc is not None
                and (
                    isinstance(exc, ConnectionError)
                    or "connection lost" in exc_str.lower()
                    or "broken pipe" in exc_str.lower()
                )
            )
            if is_connection_error:
                structlog.get_logger().warning(
                    "asyncio_connection_lost",
                    message=msg,
                    exception=exc_str,
                )
            else:
                structlog.get_logger().error(
                    "asyncio_unhandled",
                    message=msg,
                    exception=exc,
                    **{k: v for k, v in context.items() if k not in ("message", "exception")},
                )
                if alert_chat_id:
                    text = f"⚠️ Editor-bot: {msg}\n{exc_str}"[:4000]
                    asyncio.create_task(send_alert(bot, alert_chat_id, text, "asyncio_unhandled"))

        loop.set_exception_handler(_asyncio_exception_handler)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        target_fallback = (config.TARGET_CHANNEL_ID or "").strip()
        inject = DataInjectionMiddleware(
            pool,
            target_channel_id=target_fallback,
            pdf_storage_path=config.PDF_STORAGE_PATH,
            super_admin_id=config.EDITOR_CHAT_ID,
            bot=bot,
            userbot_api_url=config.USERBOT_API_URL,
            userbot_api_token=config.USERBOT_API_TOKEN,
            alert_chat_id=config.ALERT_CHAT_ID,
        )
        editor_only = EditorOnlyMiddleware(pool, fallback_editor_chat_id=config.EDITOR_CHAT_ID)
        admin_panel = AdminPanelMiddleware(pool, super_admin_id=config.EDITOR_CHAT_ID)
        dp.update.middleware(inject)
        dp.message.middleware(editor_only)
        dp.callback_query.middleware(editor_only)
        dp.include_router(commands.router)
        dp.include_router(review.router)
        admin.router.message.middleware(admin_panel)
        admin.router.callback_query.middleware(admin_panel)
        dp.include_router(admin.router)

        path = config.EDITOR_BOT_WEBHOOK_PATH.strip() or "/incoming/post"
        webhook_token = (config.EDITOR_BOT_WEBHOOK_TOKEN or "").strip()
        if not webhook_token:
            log.error("webhook_token_required", msg="EDITOR_BOT_WEBHOOK_TOKEN must be set when running webhook server")
            sys.exit(1)
        app = create_app(
            pool, bot, config.EDITOR_CHAT_ID, path,
            webhook_token=webhook_token,
            pdf_storage_path=config.PDF_STORAGE_PATH,
            alert_chat_id=config.ALERT_CHAT_ID,
        )
        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "0.0.0.0", config.WEBHOOK_SERVER_PORT)
        await site.start()
        log.info("webhook_server_started", port=config.WEBHOOK_SERVER_PORT, path=path)

        scheduler_task = asyncio.create_task(
            run_scheduler(
                pool,
                bot,
                config.PDF_STORAGE_PATH,
                interval=30,
                userbot_api_url=config.USERBOT_API_URL,
                userbot_api_token=config.USERBOT_API_TOKEN,
                alert_chat_id=config.ALERT_CHAT_ID,
            ),
        )
        try:
            await dp.start_polling(bot)
        finally:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
            await bot.session.close()
            await runner.cleanup()
            await close_pool(pool)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("shutdown")
    except Exception as e:
        log.error("fatal", exc_info=True, error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
