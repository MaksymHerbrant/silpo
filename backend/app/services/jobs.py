"""Фонові задачі з кешем.

Аналіз чеків і збірка кошика тривають десятки секунд: це десятки викликів MCP
із тротлінгом проти 429. HTTP-запит такої довжини рве і тунель, і мобільна
мережа — звідси 502 у Mini App.

Тому кожна довга операція працює так:
    POST  ...        -> ставить задачу у фон, одразу повертає {"status": "started"}
    GET   ...        -> віддає кеш і прапорець building
Клієнт опитує GET, поки building=true, і показує часткові дані щойно вони є.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

log = logging.getLogger("jobs")

DEFAULT_TTL = 900  # 15 хвилин

_cache: dict[str, tuple[float, Any]] = {}
_running: dict[str, bool] = {}
_errors: dict[str, str] = {}
_failures: dict[str, int] = {}

# Скільки разів поспіль можна перезапускати задачу, що падає.
# Без цієї межі кожне опитування статусу стартувало нову спробу, і клієнт
# вічно бачив «будується», хоча насправді задача щоразу помирала.
MAX_CONSECUTIVE_FAILURES = 2


def _key(name: str, user_id: str) -> str:
    return f"{name}:{user_id}"


def get_cached(name: str, user_id: str, ttl: int = DEFAULT_TTL) -> Any | None:
    entry = _cache.get(_key(name, user_id))
    if not entry:
        return None
    ts, value = entry
    return value if time.time() - ts < ttl else None


def put(name: str, user_id: str, value: Any) -> None:
    _cache[_key(name, user_id)] = (time.time(), value)


def invalidate(name: str, user_id: str) -> None:
    _cache.pop(_key(name, user_id), None)


def is_running(name: str, user_id: str) -> bool:
    return bool(_running.get(_key(name, user_id)))


def last_error(name: str, user_id: str) -> str | None:
    return _errors.get(_key(name, user_id))


async def start(
    name: str, user_id: str, factory: Callable[[], Awaitable[Any]]
) -> dict[str, Any]:
    """Запускає задачу у фоні, якщо вона ще не виконується."""
    key = _key(name, user_id)
    if _running.get(key):
        return {"status": "already_running"}
    _running[key] = True
    _errors.pop(key, None)

    async def _run() -> None:
        try:
            put(name, user_id, await factory())
            _failures[key] = 0
        except Exception as exc:  # noqa: BLE001
            _errors[key] = str(exc)[:300] or type(exc).__name__
            _failures[key] = _failures.get(key, 0) + 1
            log.exception("фонова задача %s впала", key)
        finally:
            _running[key] = False

    asyncio.create_task(_run())
    return {"status": "started"}


def failures(name: str, user_id: str) -> int:
    return _failures.get(_key(name, user_id), 0)


def reset_failures(name: str, user_id: str) -> None:
    _failures[_key(name, user_id)] = 0
    _errors.pop(_key(name, user_id), None)


async def cached_or_start(
    name: str,
    user_id: str,
    factory: Callable[[], Awaitable[Any]],
    ttl: int = DEFAULT_TTL,
) -> dict[str, Any]:
    """Повертає кеш; якщо його немає — ставить задачу і віддає building=true.

    Якщо задача падає підряд кілька разів — перестаємо її перезапускати й
    повертаємо помилку. Інакше клієнт опитує статус вічно, а користувач
    дивиться на спінер, який ніколи не зникне.
    """
    cached = get_cached(name, user_id, ttl)
    if cached is not None:
        return {**cached, "building": is_running(name, user_id), "cached": True}

    if is_running(name, user_id):
        return {"building": True, "cached": False}

    if failures(name, user_id) >= MAX_CONSECUTIVE_FAILURES:
        return {
            "building": False,
            "cached": False,
            "has_data": False,
            "error": last_error(name, user_id),
            "reason": (
                "Не вдалось прочитати дані Сільпо: "
                f"{last_error(name, user_id) or 'зʼєднання обірвалось'}"
            ),
        }

    await start(name, user_id, factory)
    return {"building": True, "cached": False}
