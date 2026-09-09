"""Валідація Telegram WebApp initData.

Алгоритм (офіційна документація Telegram, розділ "Validating data received
via the Mini App"):

1. initData приходить як urlencoded query-рядок:
   ``query_id=...&user=%7B...%7D&auth_date=...&hash=...``
2. Виймаємо ТІЛЬКИ поле ``hash``, решту пар (включно з ``signature``, якщо
   Telegram його прислав) сортуємо за ключем і склеюємо у data_check_string
   у форматі ``key=value`` через ``\n``.

   Важливо: ``signature`` (Ed25519, Bot API 7.10+) призначений для валідації
   третьою стороною БЕЗ токена бота, але з data_check_string він НЕ
   виключається — його виключають лише у власне Ed25519-перевірці. Якщо
   викинути його тут, HMAC не зійдеться на цілком справжніх даних.
3. secret_key = HMAC_SHA256(key="WebAppData", msg=<bot_token>)
   — зверни увагу: тут bot token є ПОВІДОМЛЕННЯМ, а "WebAppData" ключем.
4. Очікуваний хеш = hex(HMAC_SHA256(key=secret_key, msg=data_check_string)).
5. Порівнюємо у constant-time з отриманим ``hash``.
6. Додатково перевіряємо ``auth_date`` на свіжість (anti-replay).

Без цієї перевірки будь-хто може підробити telegram_id, надіславши
довільний initData у наш API.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    language_code: str | None
    start_param: str | None = None


def _data_check_string(pairs: list[tuple[str, str]]) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(pairs, key=lambda p: p[0]))


def verify_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> TelegramUser:
    if not bot_token:
        raise InitDataError("TELEGRAM_BOT_TOKEN не налаштований на бекенді")
    if not init_data:
        raise InitDataError("Порожній initData")

    # keep_blank_values: Telegram може прислати порожні значення, вони теж входять у підпис.
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    received_hash: str | None = None
    rest: list[tuple[str, str]] = []
    for key, value in pairs:
        if key == "hash":
            received_hash = value
        else:
            rest.append((key, value))

    if not received_hash:
        raise InitDataError("У initData немає поля hash")

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, _data_check_string(rest).encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("Підпис initData не збігається — дані підроблені")

    data = dict(rest)

    auth_date = data.get("auth_date")
    if not auth_date or not auth_date.isdigit():
        raise InitDataError("Відсутній або некоректний auth_date")
    age = time.time() - int(auth_date)
    if age > max_age_seconds:
        raise InitDataError(f"initData протух ({int(age)}s > {max_age_seconds}s)")

    raw_user = data.get("user")
    if not raw_user:
        raise InitDataError("У initData немає об'єкта user")
    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError as exc:
        raise InitDataError("Поле user не є валідним JSON") from exc

    if "id" not in user:
        raise InitDataError("У user немає id")

    return TelegramUser(
        telegram_id=int(user["id"]),
        username=user.get("username"),
        first_name=user.get("first_name"),
        language_code=user.get("language_code"),
        start_param=data.get("start_param"),
    )
