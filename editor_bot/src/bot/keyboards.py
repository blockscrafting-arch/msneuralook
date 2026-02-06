"""Inline keyboards for editor actions."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def review_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """
    Build inline keyboard: Опубликовать | Редактировать | Отклонить.

    Args:
        post_id: Post id for callback_data.

    Returns:
        InlineKeyboardMarkup with three buttons.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton(text="✏ Редактировать", callback_data=f"edit_{post_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{post_id}"),
        ],
    ])
