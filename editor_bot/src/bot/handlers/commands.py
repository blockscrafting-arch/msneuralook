"""Handlers for /start, /status, /help."""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
import structlog

from src.database.repository import get_post_counts_by_status

log = structlog.get_logger()

router = Router(name="commands")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Respond to /start."""
    await message.answer(
        "Бот для утверждения постов. Новые посты с саммари приходят с кнопками: "
        "Опубликовать, Редактировать, Отклонить."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Respond to /help."""
    await message.answer(
        "Команды: /start, /help, /status. "
        "Когда приходит пост на утверждение — используйте кнопки под сообщением. "
        "Админы: /admin — настройки каналов, целевого канала, редакторов и админов."
    )


@router.message(Command("status"))
async def cmd_status(message: Message, pool=None) -> None:
    """Respond to /status with post counts by status from DB."""
    if not pool:
        await message.answer("Бот работает. Очередь постов смотрите в n8n или в БД.")
        return
    try:
        counts = await get_post_counts_by_status(pool)
        lines = ["По статусам:"] + [f"  {s}: {c}" for s, c in sorted(counts.items())]
        await message.answer("\n".join(lines) if counts else "Постов пока нет.")
    except Exception as e:
        log.error("status_failed", exc_info=True, error=str(e))
        await message.answer("Ошибка запроса к БД.")
