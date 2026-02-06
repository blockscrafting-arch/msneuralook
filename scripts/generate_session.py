#!/usr/bin/env python3
"""
One-time script to generate Telethon session string for userbot.

Run locally (not in Docker):
  pip install telethon pydantic-settings python-dotenv
  Copy .env.example to .env and set TELEGRAM_API_ID, TELEGRAM_API_HASH.
  Set TELEGRAM_SESSION_STRING= in .env (leave empty).
  python scripts/generate_session.py

You will be prompted for phone number and code. On success, the script
prints a session string; put it in .env as TELEGRAM_SESSION_STRING=...
"""

import asyncio
import os
import sys

# Add project root so we can load .env from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
if not API_ID or not API_HASH:
    print("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
    sys.exit(1)

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    client = TelegramClient(
        StringSession(),
        int(API_ID),
        API_HASH,
    )
    await client.start(
        phone=lambda: input("Phone (with country code, e.g. +79...): "),
        code_callback=lambda: input("Code from Telegram: "),
        password=lambda: input("2FA password (or Enter to skip): ") or None,
    )
    session_string = client.session.save()
    print("\nAdd this to your .env file:\n")
    print(f"TELEGRAM_SESSION_STRING={session_string}")
    print("\nDo not share this string. Keep .env out of git.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
