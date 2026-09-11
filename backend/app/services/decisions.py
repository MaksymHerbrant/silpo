"""Метрика цінності: що запропонували і що гість прийняв.

Єдина цифра, яку не можна намалювати в презентації. Не «подивився графік»,
а «змінив покупку».

Два принципи, від яких залежить чесність відсотка:

1. Знаменник не роздувається. Відкрита пропозиція на ту саму пару
   «товар → заміна» одна: перебудова плану не створює дубль, інакше кожні
   15 хвилин кеш псував би статистику.
2. Економія фіксується на момент ПОКАЗУ. Ціни змінюються, і перерахунок
   заднім числом за новими цінами був би підтасовкою.
"""
from __future__ import annotations

import logging
from typing import Any

from app.db import repo

log = logging.getLogger("decisions")

# Дії, які взагалі є пропозицією до гостя
PROPOSAL_ACTIONS = {"switch", "review", "add", "blocked"}

KIND_LABELS = {
    "safety": "Безпечні заміни",
    "preference": "Заміни за вподобаннями",
    "promo": "Акції на звичне",
    "health": "Здоровіші заміни",
    "alternative": "Вигідніші аналоги",
    "reminder": "Нагадування поповнити",
}


def _kind_for(item: dict[str, Any]) -> str:
    if item.get("action") == "blocked":
        return "safety"
    if item.get("action") == "add":
        return "promo"
    hits = item.get("allergen_hits") or []
    if any(h.get("action") == "swap" for h in hits):
        return "preference"
    if item.get("action") == "review":
        return "alternative"
    return "health"


def _delta_for(item: dict[str, Any]) -> float:
    alt = item.get("alternative")
    if alt:
        return round(float(alt.get("saved") or 0) * int(item.get("quantity") or 1), 2)
    if item.get("action") == "add":
        return round(float(item.get("saved") or 0) * int(item.get("quantity") or 1), 2)
    return 0.0


async def attach(user_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Реєструє показані пропозиції і вписує їх id у план.

    Помилка запису не має ламати план: метрика важлива, але не важливіша за
    те, щоб гість побачив свій кошик.
    """
    items = plan.get("items") or []
    try:
        existing = {
            (r.get("kind"), r.get("slug") or "", r.get("alt_slug") or ""): r
            for r in await repo.open_decisions(user_id)
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("не змогли прочитати відкриті рішення: %s", exc)
        return plan

    for item in items:
        if item.get("action") not in PROPOSAL_ACTIONS:
            continue
        alt = item.get("alternative")
        kind = _kind_for(item)
        key = (kind, item.get("slug") or "", (alt or {}).get("slug") or "")
        row = existing.get(key)
        if row is None:
            try:
                row = await repo.record_decision(user_id, {
                    "kind": kind,
                    "slug": item.get("slug"),
                    "alt_slug": (alt or {}).get("slug"),
                    "title": (alt or {}).get("name") or item.get("name"),
                    "price_delta": _delta_for(item),
                })
                existing[key] = row
            except Exception as exc:  # noqa: BLE001
                log.warning("пропозицію не записали: %s", exc)
                continue
        decision_id = row.get("id")
        item["decision_id"] = decision_id
        if alt is not None:
            alt["decision_id"] = decision_id

    return plan


def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Відсоток прийнятих — загалом і за типом пропозиції."""
    by_kind: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = by_kind.setdefault(
            row.get("kind") or "other",
            {"kind": row.get("kind") or "other", "shown": 0, "decided": 0,
             "accepted": 0, "saved": 0.0},
        )
        bucket["shown"] += 1
        if row.get("accepted") is None:
            continue
        bucket["decided"] += 1
        if row["accepted"]:
            bucket["accepted"] += 1
            bucket["saved"] += float(row.get("price_delta") or 0)

    kinds = []
    for bucket in by_kind.values():
        kinds.append({
            **bucket,
            "label": KIND_LABELS.get(bucket["kind"], bucket["kind"]),
            "saved": round(bucket["saved"], 2),
            "rate": (
                round(bucket["accepted"] / bucket["decided"] * 100)
                if bucket["decided"] else None
            ),
        })
    kinds.sort(key=lambda k: -k["shown"])

    shown = sum(k["shown"] for k in kinds)
    decided = sum(k["decided"] for k in kinds)
    accepted = sum(k["accepted"] for k in kinds)
    return {
        "shown": shown,
        "decided": decided,
        "accepted": accepted,
        "rate": round(accepted / decided * 100) if decided else None,
        "saved": round(sum(k["saved"] for k in kinds), 2),
        "by_kind": kinds,
        # Поки рішень мало, відсоток нічого не означає — так і кажемо
        "reliable": decided >= 5,
    }
