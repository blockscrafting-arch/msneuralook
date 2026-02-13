"""Handlers for /start, /status, /help."""

from aiogram import F, Router
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from aiogram.filters import Command
import structlog

from src.database.admin_repository import is_admin
from src.database.repository import get_post_counts_by_status
from src.bot.admin_keyboards import admin_main_keyboard, editor_admin_keyboard

log = structlog.get_logger()

router = Router(name="commands")

ADMIN_BUTTON_TEXT = "Админка"


def admin_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard with single 'Админка' button (shown at bottom)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=ADMIN_BUTTON_TEXT)]],
        resize_keyboard=True,
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Respond to /start."""
    await message.answer(
        "Бот для утверждения постов. Новые посты с саммари приходят с кнопками: "
        "Опубликовать, Редактировать, Отклонить.",
        reply_markup=admin_reply_keyboard(),
    )


@router.message(F.text == ADMIN_BUTTON_TEXT)
async def cmd_admin_button(message: Message, **kwargs: object) -> None:
    """Open admin panel: full menu for admins, limited for editors."""
    pool = kwargs.get("pool")
    if not pool:
        await message.answer("Ошибка сервера.")
        return
    if not message.from_user:
        await message.answer("Ошибка.")
        return
    is_admin_ = await is_admin(pool, message.from_user.id)
    text = "— Админ-панель —"
    if is_admin_:
        await message.answer(text, reply_markup=admin_main_keyboard())
    else:
        await message.answer(text, reply_markup=editor_admin_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Respond to /help."""
    await message.answer(
        "Команды: /start, /help, /status. "
        "Когда приходит пост на утверждение — используйте кнопки под сообщением. "
        "Кнопка «Админка» или /admin — панель настроек (каналы, маркеры, отложенные посты, промпт). "
        "Доступна редакторам и админам; разделы «Редакторы» и «Админы» — только у админов.",
        reply_markup=admin_reply_keyboard(),
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
