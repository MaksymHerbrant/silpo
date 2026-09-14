"""Telegram-бот як канал доставки звіту (не співрозмовник).

Сценарій, який показуємо журі:
  1. /start або /report -> бекенд аналізує кошик через MCP і надсилає
     звіт-світлофор у чат;
  2. другим повідомленням — персональна пропозиція заміни, текст якої
     генерує Claude з УЖЕ порахованих чисел;
  3. під нею дві inline-кнопки: «Замінити» тригерить реальний write у MCP
     (silpo_add_or_update_cart_products), «Залишити» пише accepted=false
     у метрику прийняття свопів;
  4. кнопка «Мій Нутрі-профіль» відкриває Mini App із графіками.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.bot import report, telegram_api
from app.config import get_settings
from app.db import repo
from app.llm import explain
from app.mcp.gateway import McpNotConnected
from app.security.session import current_user_id
from app.services import cart_analysis, digest, swaps, trends

router = APIRouter(tags=["bot"])
log = logging.getLogger("bot")


async def push_cart_report(user_id: str, chat_id: int) -> dict[str, Any]:
    """Звіт -> пропозиція заміни з кнопками.

    Якщо кошик не порожній — звіт по кошику (перевірка перед покупкою).
    Якщо порожній (типовий випадок) — профіль за чеками: він завжди має що сказати.
    """
    analysis = await cart_analysis.analyze_cart(user_id)
    if analysis.get("empty"):
        trend = await trends.weekly_trend(user_id, refresh=True)
        await telegram_api.send_message(
            chat_id, report.profile_report(trend), report.miniapp_keyboard()
        )
    else:
        await telegram_api.send_message(
            chat_id, report.cart_report(analysis), report.miniapp_keyboard()
        )

    suggestions = await swaps.build_suggestions(user_id, source="both")
    if not suggestions:
        return {"sent": True, "swaps": 0}

    best = suggestions[0]
    text = await explain.upsell_text(analysis, best)
    delta = None
    if best.get("suggested_price") and best.get("original_price"):
        delta = round(best["suggested_price"] - best["original_price"], 2)
    await telegram_api.send_message(
        chat_id, text, report.swap_keyboard(str(best["id"]), delta)
    )
    return {"sent": True, "swaps": len(suggestions)}


@router.post("/bot/report")
async def report_to_chat(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Кнопка з Mini App: «надіслати звіт у чат»."""
    user = await repo.get_user(user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Користувача не знайдено")
    return await push_cart_report(user_id, int(user["telegram_id"]))


@router.post("/bot/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict[str, Any]:
    """Приймає апдейти Telegram. Секрет перевіряємо обов'язково —
    інакше будь-хто зможе надсилати нам фейкові callback'и."""
    settings = get_settings()
    if settings.telegram_webhook_secret and (
        x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Невірний secret_token")

    update = await request.json()

    if "message" in update:
        await _handle_message(update["message"])
    elif "callback_query" in update:
        await _handle_callback(update["callback_query"])
    return {"ok": True}


async def _resolve_user(telegram_id: int) -> str | None:
    user = await repo.get_user_by_telegram_id(telegram_id)
    return str(user["id"]) if user else None


async def _handle_message(message: dict[str, Any]) -> None:
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip().lower()
    telegram_id = message.get("from", {}).get("id")
    if not chat_id or not telegram_id:
        return

    # /push @username — член команди надсилає нагадування іншому гостю
    # саме тоді, коли той знімає екран. Лише для ID зі списку в налаштуваннях.
    if text.startswith("/push"):
        await _handle_push(chat_id, int(telegram_id), message.get("text") or "")
        return

    user_id = await _resolve_user(int(telegram_id))
    if not user_id:
        await telegram_api.send_message(
            chat_id,
            "👋 Це <b>Нутрі-Кошик</b> — аналіз ваших покупок у Сільпо.\n\n"
            "Відкрийте застосунок кнопкою нижче й під'єднайте акаунт Сільпо — "
            "після цього я надсилатиму сюди звіт по кошику.",
            report.miniapp_keyboard(),
        )
        return

    if text.startswith(("/start", "/report", "звіт")):
        try:
            await push_cart_report(user_id, chat_id)
        except McpNotConnected:
            await telegram_api.send_message(
                chat_id,
                "Спочатку під'єднайте акаунт Сільпо у застосунку 👇",
                report.miniapp_keyboard(),
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("push_cart_report впав")
            await telegram_api.send_message(chat_id, f"Не вдалось зібрати звіт: {exc}")
        return

    await telegram_api.send_message(
        chat_id,
        "Я не чат-бот 🙂 Надішліть /report, щоб отримати звіт по кошику, "
        "або відкрийте застосунок:",
        report.miniapp_keyboard(),
    )


async def _handle_push(chat_id: int, sender_id: int, raw: str) -> None:
    admins = {a.strip() for a in get_settings().demo_admin_ids.split(",") if a.strip()}
    if str(sender_id) not in admins:
        await telegram_api.send_message(chat_id, "Ця команда лише для команди GreenCart.")
        return
    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        await telegram_api.send_message(chat_id, "Кому надіслати? Напишіть: /push @username")
        return
    target = await repo.find_user(parts[1])
    if not target:
        await telegram_api.send_message(chat_id, f"Гостя «{parts[1]}» у базі немає — він має хоч раз відкрити застосунок.")
        return
    try:
        result = await digest.send_to_user(str(target["id"]), force=True, preview=True)
    except Exception as exc:  # noqa: BLE001
        log.exception("/push впав")
        await telegram_api.send_message(chat_id, f"Не вдалось: {exc}")
        return
    who = target.get("first_name") or target.get("username") or target["telegram_id"]
    if result.get("sent"):
        await telegram_api.send_message(
            chat_id, f"Надіслано {who}: нагадувань {result.get('due', 0)}, знижок {result.get('drops', 0)}."
        )
    else:
        await telegram_api.send_message(chat_id, f"Не надіслано {who}: {result.get('reason')}")


async def _handle_callback(callback: dict[str, Any]) -> None:
    data = callback.get("data") or ""
    callback_id = callback["id"]
    message = callback.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    telegram_id = callback.get("from", {}).get("id")

    if not data.startswith("swap:") or not telegram_id:
        await telegram_api.answer_callback(callback_id)
        return

    _, swap_id, action = (data.split(":") + ["", ""])[:3]
    user_id = await _resolve_user(int(telegram_id))
    if not user_id:
        await telegram_api.answer_callback(callback_id, "Спочатку увійдіть у застосунок", alert=True)
        return

    if action == "apply":
        try:
            await swaps.apply_swap(user_id, swap_id)
        except Exception as exc:  # noqa: BLE001
            log.exception("apply_swap впав")
            await telegram_api.answer_callback(callback_id, f"Не вдалось: {exc}"[:200], alert=True)
            return
        await telegram_api.answer_callback(callback_id, "Готово! Кошик оновлено")
        await telegram_api.edit_message(
            chat_id, message_id,
            (message.get("text") or "") + "\n\n✅ <b>Замінено у вашому кошику Сільпо</b>",
        )
    else:
        await swaps.decline_swap(user_id, swap_id)
        await telegram_api.answer_callback(callback_id, "Гаразд, лишаємо як є")
        await telegram_api.edit_message(
            chat_id, message_id, (message.get("text") or "") + "\n\n❌ <i>Залишено без змін</i>",
        )
