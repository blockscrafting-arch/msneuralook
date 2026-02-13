"""Inline keyboards for editor actions."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def schedule_actions_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """
    Keyboard after scheduling: cancel or reschedule.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отменить планирование", callback_data=f"cancel_schedule_{post_id}"),
            InlineKeyboardButton(text="Перепланировать", callback_data=f"reschedule_{post_id}"),
        ],
    ])


def review_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """
    Build inline keyboard: Опубликовать | Запланировать | Редактировать | Отклонить.

    Args:
        post_id: Post id for callback_data.

    Returns:
        InlineKeyboardMarkup with four buttons.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton(text="📅 Запланировать", callback_data=f"schedule_{post_id}"),
        ],
        [
            InlineKeyboardButton(text="✏ Редактировать", callback_data=f"edit_{post_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{post_id}"),
        ],
    ])
