"""Отправка оповещений в Telegram при критических ошибках (с троттлингом)."""

import time
from typing import Optional

from aiogram import Bot

# Минимальный интервал между алертами одного типа (секунды)
ALERT_THROTTLE_SEC = 900  # 15 минут

_last_sent: dict[str, float] = {}


async def send_alert(
    bot: Bot,
    chat_id: int,
    message: str,
    alert_key: str = "default",
) -> bool:
    """
    Отправить сообщение в Telegram. Если за последние ALERT_THROTTLE_SEC уже
    отправлялся алерт с тем же alert_key — не отправлять (вернуть False).
    """
    now = time.monotonic()
    if alert_key in _last_sent and (now - _last_sent[alert_key]) < ALERT_THROTTLE_SEC:
        return False
    try:
        await bot.send_message(chat_id, message[:4000])
        _last_sent[alert_key] = now
        return True
    except Exception:
        return False
