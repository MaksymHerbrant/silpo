"""Сесія Mini App: підписаний JWT, який фронтенд шле у Authorization: Bearer."""
from __future__ import annotations

import time

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import get_settings

ALGO = "HS256"


def issue_session(user_id: str, telegram_id: int) -> tuple[str, int]:
    s = get_settings()
    exp = int(time.time()) + s.session_ttl_seconds
    token = jwt.encode(
        {"sub": user_id, "tg": telegram_id, "exp": exp, "iat": int(time.time())},
        s.session_secret,
        algorithm=ALGO,
    )
    return token, exp


def decode_session(token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(token, s.session_secret, algorithms=[ALGO])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Невалідна сесія: {exc}") from exc


async def current_user_id(authorization: str = Header(default="")) -> str:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Немає Bearer-токена сесії")
    payload = decode_session(authorization.split(" ", 1)[1].strip())
    return str(payload["sub"])


CurrentUser = Depends(current_user_id)
