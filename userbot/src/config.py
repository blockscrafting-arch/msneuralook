"""Configuration loaded from environment (pydantic Settings)."""

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

    # Source channel to monitor (username or -100... ID)
    SOURCE_CHANNEL: str

    # n8n webhook URL (POST here when new PDF post appears)
    N8N_WEBHOOK_URL: str

    # Path to directory where PDFs are saved (in Docker: /data/pdfs)
    PDF_STORAGE_PATH: str = "/data/pdfs"

    def get_source_channel_id_or_username(self) -> str:
        """Return SOURCE_CHANNEL as-is (username or numeric string)."""
        return self.SOURCE_CHANNEL.strip()
