"""Збережений результат довгих побудов.

Раніше кеш жив лише в памʼяті процесу: перезапуск бекенду або 15 хвилин
бездіяльності — і застосунок заново читав тридцять з гаком викликів MCP, щоб
показати рівно те саме. Тепер результат лежить у базі й переживає рестарт.

Єдине місце, яке вирішує «дані застаріли» — фонова перевірка новизни чеків
(services/freshness.py). Вона скидає ВСІ похідні результати одразу, бо всі
вони зроблені з тих самих чеків.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.db.supabase import db

log = logging.getLogger("cache")

TABLE = "job_cache"


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def load(user_id: str, name: str) -> dict[str, Any] | None:
    try:
        return await db().select_one(TABLE, {"user_id": user_id, "name": name})
    except Exception as exc:  # noqa: BLE001 — кеш не має валити запит
        log.warning("не прочитали кеш %s: %s", name, exc)
        return None


async def store(user_id: str, name: str, signature: str | None, payload: dict[str, Any]) -> None:
    try:
        await db().upsert(TABLE, {
            "user_id": user_id, "name": name, "signature": signature,
            "built_at": _now(), "checked_at": _now(), "payload": payload,
        }, on_conflict="user_id,name")
    except Exception as exc:  # noqa: BLE001
        log.warning("не зберегли кеш %s: %s", name, exc)


async def touch(user_id: str, name: str) -> None:
    """Позначає, що новизну щойно перевірили і дані досі актуальні."""
    try:
        await db().update(TABLE, {"user_id": user_id, "name": name}, {"checked_at": _now()})
    except Exception as exc:  # noqa: BLE001
        log.warning("не оновили checked_at для %s: %s", name, exc)


async def drop_all(user_id: str) -> None:
    """Скидає всі похідні результати гостя — після нового чека або на вимогу."""
    try:
        await db().delete(TABLE, {"user_id": user_id})
    except Exception as exc:  # noqa: BLE001
        log.warning("не скинули кеш: %s", exc)


def age_seconds(row: dict[str, Any] | None, field: str = "built_at") -> float | None:
    if not row or not row.get(field):
        return None
    try:
        when = datetime.fromisoformat(str(row[field]).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (datetime.now(UTC) - when).total_seconds()
