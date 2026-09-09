"""Тижневий тренд і звички з офлайн-чеків Сільпо.

Побудова профілю — дорога операція: 20+ чеків, до 25 викликів
silpo_get_product_details із тротлінгом. Через тунель/мобільну мережу такий
запит легко обривається, тому:

  * за замовчуванням віддаємо ГОТОВИЙ результат із кешу (памʼять + Supabase);
  * повний перерахунок робиться лише за явним refresh=true;
  * якщо кешу ще немає — рахуємо один раз і кладемо в кеш.
"""
from __future__ import annotations

import time
from typing import Any

from app.db import repo
from app.mcp.gateway import silpo
from app.services import habits
from app.services.cart_analysis import fetch_cart

CACHE_TTL = 900  # 15 хвилин
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

# Побудова профілю триває до хвилини — довше, ніж живе HTTP-запит через тунель
# (звідси були 502). Тому рахуємо у фоновій задачі, а клієнт опитує статус.
_building: dict[str, bool] = {}
_errors: dict[str, str] = {}


def is_building(user_id: str) -> bool:
    return bool(_building.get(user_id))


async def start_rebuild(user_id: str) -> dict[str, Any]:
    """Запускає перерахунок у фоні й одразу повертає керування."""
    import asyncio

    if _building.get(user_id):
        return {"status": "already_running"}
    _building[user_id] = True
    _errors.pop(user_id, None)

    async def _run() -> None:
        try:
            await rebuild(user_id)
        except Exception as exc:  # noqa: BLE001
            _errors[user_id] = str(exc)[:300]
        finally:
            _building[user_id] = False

    asyncio.create_task(_run())
    return {"status": "started"}


def _cached(user_id: str) -> dict[str, Any] | None:
    entry = _cache.get(user_id)
    if not entry:
        return None
    ts, payload = entry
    return payload if time.time() - ts < CACHE_TTL else None


def _delta(rows: list[dict[str, Any]]) -> int | None:
    scored = [r for r in rows if r.get("health_score") is not None]
    if len(scored) < 2:
        return None
    return scored[-1]["health_score"] - scored[-2]["health_score"]


async def rebuild(user_id: str) -> dict[str, Any]:
    """Повний перерахунок профілю з MCP. Довго — викликати свідомо."""
    async with silpo(user_id) as api:
        ctx, _products, meta = await fetch_cart(api)
        if ctx is None:
            return {
                "weeks": [], "delta_vs_prev_week": None, "profile": None, "habits": None,
                "reason": meta.get("reason", "Потрібен активний кошик, щоб отримати контекст магазину"),
            }
        data = await habits.build(user_id, api, ctx)

    payload = {
        "weeks": data["weeks"],
        "delta_vs_prev_week": _delta(data["weeks"]),
        "profile": data.get("profile"),
        "habits": {
            "summary": data["summary"],
            "top_products": data["top_products"],
            "categories": data["categories"],
            "orders_count": data["orders_count"],
        },
        "cached": False,
    }
    _cache[user_id] = (time.time(), payload)
    return payload


async def weekly_trend(user_id: str, refresh: bool = False) -> dict[str, Any]:
    if refresh:
        return await rebuild(user_id)

    cached = _cached(user_id)
    if cached:
        return {**cached, "cached": True, "building": is_building(user_id)}

    # Кешу в памʼяті немає (рестарт бекенду) — віддаємо збережені тижні,
    # щоб екран не був порожнім, і позначаємо, що звички треба перерахувати.
    rows = sorted(
        await repo.list_weekly_snapshots(user_id), key=lambda r: str(r["week_start_date"])
    )
    if rows:
        return {
            "weeks": rows, "delta_vs_prev_week": _delta(rows),
            "profile": None, "habits": None, "cached": True,
            "needs_refresh": True, "building": is_building(user_id),
            "error": _errors.get(user_id),
        }
    # Даних ще немає взагалі — запускаємо побудову у фоні й віддаємо порожній стан
    await start_rebuild(user_id)
    return {
        "weeks": [], "delta_vs_prev_week": None, "profile": None, "habits": None,
        "building": True, "needs_refresh": True,
    }
