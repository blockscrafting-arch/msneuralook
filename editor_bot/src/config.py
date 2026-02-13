"""Configuration loaded from environment (pydantic Settings)."""

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Editor bot settings. All secrets from env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    DATABASE_URL: str
    # Bootstrap/fallback: first admin and target channel (optional after DB is configured)
    EDITOR_CHAT_ID: Optional[int] = None  # Telegram user ID for bootstrap + webhook recipient
    TARGET_CHANNEL_ID: Optional[str] = None  # Target channel for publishing (e.g. -1001234567890)
    EDITOR_BOT_WEBHOOK_PATH: str = "/incoming/post"
    EDITOR_BOT_WEBHOOK_TOKEN: str = ""  # if set, require Authorization: Bearer <token>
    PDF_STORAGE_PATH: str = "/data/pdfs"
    WEBHOOK_SERVER_PORT: int = 8080

    # Userbot API: resolve discussion message id for PDF in linked group (optional)
    USERBOT_API_URL: Optional[str] = None  # e.g. http://userbot:8081
    USERBOT_API_TOKEN: Optional[str] = None

    # Оповещения в Telegram при критических ошибках (user ID, например 551570137)
    ALERT_CHAT_ID: Optional[int] = None

    # Прокси для запросов к Telegram (Bot API). Если пусто — используется HTTP_PROXY из env.
    TELEGRAM_PROXY: Optional[str] = None

    @field_validator("EDITOR_CHAT_ID")
    @classmethod
    def editor_chat_id_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if not v or v == 0:
            raise ValueError("EDITOR_CHAT_ID must be a non-zero Telegram user ID")
        return v

    @field_validator("TARGET_CHANNEL_ID")
    @classmethod
    def target_channel_strip(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return v.strip() or None
