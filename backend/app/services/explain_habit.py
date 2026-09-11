"""Чому конкретного товару немає у звичному наборі.

Питання «я ж завжди це беру, чому його тут нема?» — найчастіше й
найсправедливіше. Відповідь не можна давати загальними словами: потрібні
дати покупок і та сама перевірка, яку товар проходив у конвеєрі.

Цей модуль нічого не вирішує наново — він ПОКАЗУЄ вже ухвалене рішення
і називає конкретну умову, що не виконалась.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services import habit_model, kinds
from app.services import noise as noise_filter

MAX_MATCHES = 6


def _fail_reason(habit: Any, days_in_window: int, weeks_in_window: int) -> str:
    """Яка саме умова не виконалась. Без загальних слів."""
    if habit.days < habit_model.MIN_DAYS_FOR_REPEAT:
        return "куплено лише в один день — повторення ще не було"
    if habit.kind == habit_model.FADING:
        return f"остання покупка {habit.since_last_days} дн. тому — ритм обірвався"
    if days_in_window < habit_model.STABLE_MIN_DAYS:
        return (
            f"за останні {habit_model.RECENT_WINDOW_DAYS} дн. покупок було "
            f"{days_in_window}, а для звички потрібно {habit_model.STABLE_MIN_DAYS}"
        )
    if weeks_in_window < habit_model.STABLE_MIN_WEEKS:
        return (
            f"покупки припали на {weeks_in_window} різних тижні, а потрібно "
            f"щонайменше {habit_model.STABLE_MIN_WEEKS}"
        )
    return "умови звички виконані"


def explain(rows: list[dict[str, Any]], query: str, period_days: int,
            today: date | None = None) -> dict[str, Any]:
    """rows — агрегати з plan._aggregate (по SKU, ще не згруповані у види)."""
    today = today or date.today()
    needle = (query or "").strip().lower()
    if len(needle) < 3:
        return {"query": query, "matches": [], "found": 0,
                "reason": "Введіть щонайменше три літери"}

    matched = [r for r in rows if needle in (r.get("name") or "").lower()]
    matched.sort(key=lambda r: -len(r.get("days") or []))

    grouped = kinds.group(matched) if matched else []
    by_kind = {g.get("kind_key"): g for g in grouped}

    out: list[dict[str, Any]] = []
    for row in matched[:MAX_MATCHES]:
        days = row.get("days") or []
        kind = kinds.kind_of(row.get("name") or "")
        group = by_kind.get(kind) or row
        kind_days = group.get("days") or days
        cycle = noise_filter.cycle_for(row.get("name") or "")

        # Звичку перевіряємо на рівні ВИДУ — так само, як у справжньому конвеєрі
        habit = habit_model.analyse(kind_days, period_days, cycle, today)
        cutoff = today.toordinal() - habit_model.RECENT_WINDOW_DAYS
        recent = [d for d in kind_days if date.fromisoformat(d).toordinal() >= cutoff]
        weeks_recent = len({date.fromisoformat(d).isocalendar()[:2] for d in recent})

        out.append({
            "name": row.get("name"),
            "slug": row.get("slug"),
            "kind": kind,
            "purchase_days": days,
            "days_total": len(days),
            "days_in_kind": len(kind_days),
            "brands_in_kind": group.get("kind_brands", 1),
            "days_recent": len(recent),
            "weeks_recent": weeks_recent,
            "cycle_days": cycle,
            "verdict": habit.kind,
            "verdict_label": habit_model.LABELS.get(habit.kind, habit.kind),
            "is_habit": habit.kind == habit_model.STABLE,
            "explanation": habit.reason,
            "why_not": None if habit.kind == habit_model.STABLE
                       else _fail_reason(habit, len(recent), weeks_recent),
        })

    return {
        "query": query,
        "period_days": period_days,
        "window_days": habit_model.RECENT_WINDOW_DAYS,
        "rules": {
            "min_days_for_repeat": habit_model.MIN_DAYS_FOR_REPEAT,
            "stable_min_days": habit_model.STABLE_MIN_DAYS,
            "stable_min_weeks": habit_model.STABLE_MIN_WEEKS,
        },
        "matches": out,
        "found": len(matched),
    }
