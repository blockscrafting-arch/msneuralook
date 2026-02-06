"""Entry point: configure logging, load config, run Telethon client and monitor channel."""

import asyncio
import sys

import structlog

from src.config import Settings
from src.utils.logging import configure_logging
from src.client import create_client
from src.handlers.new_post import register_new_post_handler


def main() -> None:
    """Run userbot: connect to Telegram and process new PDF posts."""
    configure_logging()
    log = structlog.get_logger()

    try:
        config = Settings()
    except Exception as e:
        structlog.get_logger().error("config_load_failed", error=str(e), exc_info=True)
        sys.exit(1)

    source = config.get_source_channel_id_or_username()
    if not config.N8N_WEBHOOK_URL or not source or not config.TELEGRAM_SESSION_STRING:
        log.error("missing_config", msg="Set TELEGRAM_SESSION_STRING, SOURCE_CHANNEL, N8N_WEBHOOK_URL in .env")
        sys.exit(1)

    client = create_client(
        api_id=config.TELEGRAM_API_ID,
        api_hash=config.TELEGRAM_API_HASH,
        session_string=config.TELEGRAM_SESSION_STRING,
    )

    register_new_post_handler(client, config)

    log.info("userbot_starting", source_channel=source)

    with client:
        client.run_until_disconnected()


if __name__ == "__main__":
    main()
