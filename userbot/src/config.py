"""Configuration loaded from environment (pydantic Settings)."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Userbot settings. All secrets and channel IDs from env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram (userbot account @riskerlb)
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_SESSION_STRING: str

    # PostgreSQL (to read source_channels for monitoring)
    DATABASE_URL: str

    # Fallback source channel when DB has no channels (optional)
    SOURCE_CHANNEL: Optional[str] = None

    # n8n webhook URL (POST here when new PDF post appears)
    N8N_WEBHOOK_URL: str

    # Path to directory where PDFs are saved (in Docker: /data/pdfs)
    PDF_STORAGE_PATH: str = "/data/pdfs"

    # Internal API for editor-bot: resolve discussion message id (MTProto)
    USERBOT_API_PORT: int = 8081
    USERBOT_API_TOKEN: Optional[str] = None

    # Прокси для MTProto (Telegram). Если пусто — используется HTTP_PROXY из env.
    TELEGRAM_PROXY: Optional[str] = None

    # Буфер outbox: пауза в минутах между отправкой постов в n8n; 0 — отключено.
    OUTBOX_BUFFER_MINUTES: int = 0

    def get_source_channel_fallback(self) -> str:
        """Return SOURCE_CHANNEL as-is for fallback when DB is empty."""
        return (self.SOURCE_CHANNEL or "").strip()
