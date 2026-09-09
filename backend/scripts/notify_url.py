"""Розсилає користувачам свіжу кнопку запуску Mini App.

Безкоштовний тунель змінює URL при кожному перепідключенні. Кнопка меню бота
оновлюється через Bot API, але якщо застосунок уже відкритий — користувач
бачить «no tunnel here». Тому на кожну зміну адреси шлемо в чат повідомлення
з inline-кнопкою web_app, яка гарантовано веде на актуальний URL.

    .venv/bin/python scripts/notify_url.py --url https://xxxx.lhr.life
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    args = ap.parse_args()

    from app.bot import telegram_api
    from app.db.supabase import db

    users = await db().select("users")
    if not users:
        print("Користувачів у БД немає — нікому слати")
        return 0

    keyboard = [[{"text": "📊 Відкрити Нутрі-Кошик", "web_app": {"url": args.url}}]]
    sent = 0
    for user in users:
        try:
            await telegram_api.send_message(
                int(user["telegram_id"]),
                "🔄 Адресу тестового стенду оновлено. Відкривайте застосунок цією кнопкою:",
                keyboard,
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  не вдалось {user['telegram_id']}: {exc}")
    print(f"Надіслано: {sent}")
    await db().aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
