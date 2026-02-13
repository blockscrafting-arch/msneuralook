#!/usr/bin/env python3
"""
Разовая рассылка: отправить всем редакторам и админам сообщение с Reply-клавиатурой «Админка».

После деплоя кнопки «Админка» запустите один раз, чтобы у текущих пользователей
появилась клавиатура без необходимости нажимать /start.

Запуск из каталога editor_bot:
  PYTHONPATH=. python scripts/send_admin_keyboard_to_all.py

Или из корня проекта (с .env в корне):
  cd editor_bot && PYTHONPATH=. python scripts/send_admin_keyboard_to_all.py
"""
import asyncio
import os
import sys

# Чтобы импорты src.* работали при запуске из editor_bot
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import structlog

from src.config import Settings
from src.database.connection import create_pool_with_retry, close_pool
from src.database.admin_repository import get_admin_user_ids, get_editor_user_ids
from src.bot.handlers.commands import admin_reply_keyboard

log = structlog.get_logger()

MESSAGE = (
    "В боте появилась кнопка «Админка» внизу экрана — по нажатию открывается панель настроек "
    "(каналы, маркеры, отложенные посты, промпт). Пользоваться можно сразу."
)


async def main() -> None:
    try:
        config = Settings()
    except Exception as e:
        log.error("config_load_failed", error=str(e))
        sys.exit(1)
    if not config.BOT_TOKEN or not config.DATABASE_URL:
        log.error("missing_config", msg="Set BOT_TOKEN and DATABASE_URL in .env")
        sys.exit(1)

    pool = await create_pool_with_retry(config.DATABASE_URL)
    try:
        editor_ids = await get_editor_user_ids(pool)
        admin_ids = await get_admin_user_ids(pool)
        if not editor_ids and config.EDITOR_CHAT_ID is not None:
            editor_ids = {config.EDITOR_CHAT_ID}
        if not admin_ids and config.EDITOR_CHAT_ID is not None:
            admin_ids = {config.EDITOR_CHAT_ID}
        user_ids = editor_ids | admin_ids
        if not user_ids:
            log.warning("no_users", msg="Нет редакторов и админов в БД. Добавьте через админку или задайте EDITOR_CHAT_ID.")
            return
        log.info("sending_keyboard", count=len(user_ids), user_ids=list(user_ids))
    finally:
        await close_pool(pool)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    keyboard = admin_reply_keyboard()
    ok = 0
    fail = 0
    for uid in user_ids:
        try:
            await bot.send_message(
                uid,
                MESSAGE,
                reply_markup=keyboard,
            )
            ok += 1
            log.info("sent", user_id=uid)
        except Exception as e:
            fail += 1
            log.warning("send_failed", user_id=uid, error=str(e))
        await asyncio.sleep(0.05)
    await bot.session.close()
    log.info("done", ok=ok, fail=fail)


if __name__ == "__main__":
    asyncio.run(main())
