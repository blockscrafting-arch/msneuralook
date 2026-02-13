"""Entry point: configure logging, load config, run Telethon client and monitor channel."""

import asyncio
import os
import sys

import aiohttp.web as web
import structlog

from src.config import Settings
from src.utils.logging import configure_logging
from src.client import create_client, _parse_proxy_url
from src.database.connection import create_pool_with_retry, close_pool
from src.handlers.new_post import register_new_post_handler
from src.services.outbox_worker import run_outbox_worker
from src.web.app import create_app


def main() -> None:
    """Run userbot: connect to Telegram and process new PDF posts."""
    configure_logging()
    log = structlog.get_logger()

    try:
        config = Settings()
    except Exception as e:
        structlog.get_logger().error("config_load_failed", error=str(e), exc_info=True)
        sys.exit(1)

    if not config.N8N_WEBHOOK_URL or not config.TELEGRAM_SESSION_STRING or not config.DATABASE_URL:
        log.error(
            "missing_config",
            msg="Set TELEGRAM_SESSION_STRING, DATABASE_URL, N8N_WEBHOOK_URL in .env",
        )
        sys.exit(1)

    async def run() -> None:
        pool = await create_pool_with_retry(config.DATABASE_URL)
        proxy_url = (config.TELEGRAM_PROXY or os.environ.get("HTTP_PROXY") or "").strip()
        proxy_tuple = None
        if proxy_url:
            try:
                proxy_tuple = _parse_proxy_url(proxy_url)
                log.info("telegram_proxy_enabled", proxy_host=proxy_tuple[1], proxy_port=proxy_tuple[2])
            except Exception as e:
                log.warning("telegram_proxy_parse_failed", error=str(e))
        client = create_client(
            api_id=config.TELEGRAM_API_ID,
            api_hash=config.TELEGRAM_API_HASH,
            session_string=config.TELEGRAM_SESSION_STRING,
            proxy=proxy_tuple,
        )
        register_new_post_handler(client, config, pool)
        fallback = config.get_source_channel_fallback()
        log.info("userbot_starting", source_fallback=fallback or "(from DB)")
        try:
            async with client:
                api_app = create_app(client, config.USERBOT_API_TOKEN)
                runner = web.AppRunner(api_app)
                await runner.setup()
                site = web.TCPSite(runner, "0.0.0.0", config.USERBOT_API_PORT)
                await site.start()
                log.info("userbot_api_started", port=config.USERBOT_API_PORT)
                worker_task = asyncio.create_task(
                    run_outbox_worker(pool, config.N8N_WEBHOOK_URL),
                )
                try:
                    await client.run_until_disconnected()
                finally:
                    worker_task.cancel()
                    try:
                        await worker_task
                    except asyncio.CancelledError:
                        pass
        finally:
            await close_pool(pool)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("userbot_shutdown")
    except Exception as e:
        log.error("fatal", exc_info=True, error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
