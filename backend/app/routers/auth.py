from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import get_settings
from app.db import repo
from app.mcp import oauth
from app.security.session import current_user_id, issue_session
from app.security.telegram_auth import InitDataError, verify_init_data
from app.services import cache, jobs

from fastapi import Depends

router = APIRouter(tags=["auth"])


class TelegramAuthIn(BaseModel):
    init_data: str


class TelegramAuthOut(BaseModel):
    token: str
    expires_at: int
    user: dict
    silpo_connected: bool


@router.post("/auth/telegram", response_model=TelegramAuthOut)
async def auth_telegram(payload: TelegramAuthIn) -> TelegramAuthOut:
    """Валідує initData (HMAC-SHA256) і видає сесію Mini App."""
    s = get_settings()
    try:
        tg = verify_init_data(payload.init_data, s.telegram_bot_token, s.telegram_initdata_max_age)
    except InitDataError as exc:
        # Діагностика: без сирого рядка неможливо зрозуміти, ЩО саме не зійшлось.
        # У логи йде лише префікс і перелік полів — сам hash не друкуємо.
        from urllib.parse import parse_qsl

        try:
            keys = [k for k, _ in parse_qsl(payload.init_data, keep_blank_values=True)]
        except Exception:  # noqa: BLE001
            keys = ["<не розпарсилось>"]
        logging.warning(
            "initData відхилено: %s | довжина=%d | поля=%s | сирий=%r",
            exc, len(payload.init_data), keys, payload.init_data,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    user = await repo.upsert_user(
        tg.telegram_id,
        username=tg.username,
        first_name=tg.first_name,
        language_code=tg.language_code,
    )
    user_id = str(user["id"])

    # Повернення з зовнішнього браузера після OAuth: startapp=<one-time token>
    if tg.start_param:
        linked_user = await repo.consume_startapp_token(tg.start_param)
        if linked_user and linked_user != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "startapp-токен належить іншому користувачу")

    token, exp = issue_session(user_id, tg.telegram_id)
    tokens = await repo.get_tokens(user_id)
    return TelegramAuthOut(
        token=token,
        expires_at=exp,
        user={
            "id": user_id,
            "telegram_id": tg.telegram_id,
            "first_name": tg.first_name,
            "username": tg.username,
        },
        silpo_connected=bool(tokens) or s.demo_mode,
    )


@router.get("/auth/silpo/status")
async def silpo_status(user_id: str = Depends(current_user_id)) -> dict:
    tokens = await repo.get_tokens(user_id)
    return {
        "connected": bool(tokens) or get_settings().demo_mode,
        "demo_mode": get_settings().demo_mode,
        # Сам токен не повертаємо НІКОЛИ — лише факт наявності й строк дії.
        "expires_at": tokens["expires_at"].isoformat() if tokens else None,
    }


@router.post("/auth/silpo/start")
async def silpo_start(user_id: str = Depends(current_user_id)) -> dict:
    """Повертає URL авторизації Сільпо.

    Фронтенд ВІДКРИВАЄ його через Telegram.WebApp.openLink() — у зовнішньому
    браузері, бо WebView Telegram нестабільно тримає сторонні OAuth-popup'и.
    """
    if get_settings().demo_mode:
        return {"demo_mode": True, "authorize_url": None}
    url = await oauth.build_authorize_url(user_id)
    return {"authorize_url": url, "redirect_uri": oauth.redirect_uri()}


@router.get("/auth/silpo/callback")
async def silpo_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Колбек OAuth. Обмінює code на токени й повертає користувача в Mini App."""
    s = get_settings()
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"OAuth помилка: {error}")
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Немає code або state")

    saved = await repo.consume_oauth_state(state)
    if not saved:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Невалідний або протухлий state")

    data = await oauth.exchange_code(code, saved["code_verifier"])
    if "access_token" not in data:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Відповідь token endpoint без access_token")

    await repo.save_tokens(
        saved["user_id"],
        data["access_token"],
        data.get("refresh_token"),
        int(data.get("expires_in", 3600)),
        data.get("scope"),
        data.get("token_type", "Bearer"),
    )

    startapp = await repo.issue_startapp_token(saved["user_id"])
    if not s.telegram_bot_username:
        return {"connected": True, "note": "TELEGRAM_BOT_USERNAME не заданий — поверніться в Mini App вручну"}
    return RedirectResponse(oauth.miniapp_return_url(startapp), status_code=302)


@router.post("/auth/silpo/disconnect")
async def silpo_disconnect(user_id: str = Depends(current_user_id)) -> dict:
    """Вихід з акаунта: відкликаємо доступ до Сільпо і чистимо все похідне.

    Налаштування й історію рішень лишаємо — якщо гість повернеться, його
    поріг і режим мають бути на місці, а не питатись заново.
    """
    await repo.drop_tokens(user_id)
    await cache.drop_all(user_id)
    await repo.cart_clear(user_id)
    for name in ("plan_next", "insights", "usual", "coupons",
                 "nutrition:week", "nutrition:month", "nutrition:all"):
        jobs.invalidate(name, user_id)
        jobs.reset_failures(name, user_id)
    return {"connected": False, "cleared": True}
