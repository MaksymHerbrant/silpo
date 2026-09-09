"""Мінімальна реєстрація Telegram-бота як ТОЧКИ ВХОДУ у Mini App.

Продукт — не чат-бот. Бот потрібен лише тому, що Telegram інакше не вміє
запускати Web App. Скрипт налаштовує кнопку меню й команду /start; жодної
діалогової логіки тут немає.

    cd backend && .venv/bin/python scripts/setup_bot.py --webapp-url https://<фронтенд>
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from app.config import get_settings

    ap = argparse.ArgumentParser()
    ap.add_argument("--webapp-url", required=True, help="https URL фронтенду Mini App")
    args = ap.parse_args()

    token = get_settings().telegram_bot_token
    if not token:
        print("TELEGRAM_BOT_TOKEN не заданий у .env")
        return 1
    base = f"https://api.telegram.org/bot{token}"

    with httpx.Client(timeout=15.0) as c:
        me = c.get(f"{base}/getMe").json()
        print("Бот:", me.get("result", {}).get("username"))

        r = c.post(
            f"{base}/setChatMenuButton",
            json={"menu_button": {"type": "web_app", "text": "Нутрі-Кошик",
                                  "web_app": {"url": args.webapp_url}}},
        ).json()
        print("setChatMenuButton:", r.get("ok"), r.get("description", ""))

        r = c.post(
            f"{base}/setMyCommands",
            json={"commands": [{"command": "start", "description": "Відкрити Нутрі-Кошик"}]},
        ).json()
        print("setMyCommands:", r.get("ok"))

        secret = get_settings().telegram_webhook_secret
        webhook_url = f"{args.webapp_url.rstrip('/')}/bot/webhook"
        r = c.post(f"{base}/setWebhook", json={
            "url": webhook_url,
            "secret_token": secret,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": True,
        }).json()
        print("setWebhook:", r.get("ok"), webhook_url, r.get("description", ""))

        r = c.post(
            f"{base}/setMyDescription",
            json={"description": "Аналіз здоров'я твого кошика Сільпо. Відкрий Mini App кнопкою меню."},
        ).json()
        print("setMyDescription:", r.get("ok"))

    print(
        "\nЩе один крок вручну в @BotFather: /newapp -> обери бота -> вкажи short name "
        "(TELEGRAM_WEBAPP_SHORT_NAME) і той самий URL.\n"
        "Саме short name робить робочим deep link t.me/<bot>/<app>?startapp=<token>, "
        "через який користувач повертається після OAuth Сільпо."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
