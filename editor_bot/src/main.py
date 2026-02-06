"""Entry point: aiogram bot (polling) + aiohttp webhook server for n8n."""

import asyncio
import sys

import aiohttp.web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import Settings
from src.utils.logging import configure_logging
from src.database.connection import create_pool, close_pool
from src.bot.handlers import commands, review
from src.bot.middlewares import DataInjectionMiddleware, EditorOnlyMiddleware
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
        pool = await create_pool(config.DATABASE_URL)
        bot = Bot(
            token=config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        editor_chat_id = config.EDITOR_CHAT_ID
        inject = DataInjectionMiddleware(
            pool,
            editor_chat_id,
            config.TARGET_CHANNEL_ID.strip(),
        )
        editor_only = EditorOnlyMiddleware(editor_chat_id)
        dp.update.middleware(inject)
        dp.message.middleware(editor_only)
        dp.callback_query.middleware(editor_only)
        dp.include_router(commands.router)
        dp.include_router(review.router)

        path = config.EDITOR_BOT_WEBHOOK_PATH.strip() or "/incoming/post"
        app = create_app(
            pool, bot, editor_chat_id, path,
            webhook_token=config.EDITOR_BOT_WEBHOOK_TOKEN or "",
        )
        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "0.0.0.0", config.WEBHOOK_SERVER_PORT)
        await site.start()
        log.info("webhook_server_started", port=config.WEBHOOK_SERVER_PORT, path=path)

        try:
            await dp.start_polling(bot)
        finally:
            await bot.session.close()
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
