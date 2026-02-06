"""Configuration loaded from environment (pydantic Settings)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Editor bot settings. All secrets from env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    EDITOR_CHAT_ID: int  # Telegram user ID of the editor (only this user can use buttons)
    TARGET_CHANNEL_ID: str  # Channel ID for publishing (e.g. -1001234567890)
    DATABASE_URL: str
    EDITOR_BOT_WEBHOOK_PATH: str = "/incoming/post"
    EDITOR_BOT_WEBHOOK_TOKEN: str = ""  # if set, require Authorization: Bearer <token>
    PDF_STORAGE_PATH: str = "/data/pdfs"
    WEBHOOK_SERVER_PORT: int = 8080
