"""Мінімальний клієнт Telegram Bot API — рівно те, що потрібно для звіту.

Бот у цьому продукті НЕ співрозмовник: він надсилає готовий звіт по кошику
з inline-кнопками і відкриває Mini App. Уся логіка — в бекенді.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


def _base() -> str:
    return f"https://api.telegram.org/bot{get_settings().telegram_bot_token}"


async def _post(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(f"{_base()}/{method}", json=payload)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description')}")
    return data.get("result", {})


async def send_message(
    chat_id: int, text: str, keyboard: list[list[dict[str, Any]]] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return await _post("sendMessage", payload)


async def edit_message(chat_id: int, message_id: int, text: str,
                       keyboard: list[list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id, "message_id": message_id, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": True,
    }
    payload["reply_markup"] = {"inline_keyboard": keyboard or []}
    return await _post("editMessageText", payload)


async def answer_callback(callback_id: str, text: str = "", alert: bool = False) -> None:
    await _post("answerCallbackQuery",
                {"callback_query_id": callback_id, "text": text[:200], "show_alert": alert})


async def set_webhook(url: str, secret: str) -> dict[str, Any]:
    return await _post("setWebhook", {
        "url": url, "secret_token": secret,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    })


async def delete_webhook() -> dict[str, Any]:
    return await _post("deleteWebhook", {"drop_pending_updates": True})
