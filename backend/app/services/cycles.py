"""Цикли покупок: коли товар закінчиться і час його поповнити.

Ключова відмінність від фільтра шуму: там цикл — категорійне ПРИПУЩЕННЯ
(«молочка — раз на два тижні»), потрібне, щоб зрозуміти, чи товар узагалі
регулярний. Тут цикл — СПОСТЕРЕЖЕННЯ: медіана проміжків між реальними датами
покупок саме цього товару саме цим гостем.

Медіана, а не середнє, навмисно: одна відпустка на три тижні не має
перетворювати щотижневе молоко на «раз на місяць».

Категорійне припущення лишається запасним варіантом для товарів, куплених
один раз, — там проміжків ще немає.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any

from app.services import noise as noise_filter

# Скільки днів до розрахункової дати вважати «час поповнити»
DUE_HORIZON_DAYS = 1
# Скільки РІЗНИХ дат покупки треба, щоб довіряти спостереженню.
#
# Три, а не дві — і це не перестраховка. З двох дат виходить рівно один
# проміжок, а медіана з одного числа нічого не згладжує: дві покупки в межах
# одного тижня дали б «тютюн раз на 3 дні» і «кола раз на 2 дні». Перевірено
# на живих чеках — саме так і виходило.
MIN_PURCHASES_FOR_OBSERVED = 3
# Захист від сміття в даних
MIN_CYCLE_DAYS, MAX_CYCLE_DAYS = 2, 120


def observed_cycle(history: list[dict[str, Any]]) -> int | None:
    """Медіана проміжків між покупками. None, якщо проміжків ще немає."""
    dates = sorted({h.get("date") for h in history if h.get("date")})
    if len(dates) < MIN_PURCHASES_FOR_OBSERVED:
        return None
    parsed = [date.fromisoformat(d) for d in dates]
    gaps = [(b - a).days for a, b in zip(parsed, parsed[1:]) if (b - a).days > 0]
    if not gaps:
        return None
    return max(MIN_CYCLE_DAYS, min(MAX_CYCLE_DAYS, round(median(gaps))))


def cycle_for(name: str, history: list[dict[str, Any]], override: int | None = None) -> tuple[int, str]:
    """Повертає (цикл у днях, звідки він узявся)."""
    if override:
        return max(MIN_CYCLE_DAYS, min(MAX_CYCLE_DAYS, override)), "manual"
    seen = observed_cycle(history)
    if seen:
        return seen, "observed"
    return noise_filter.cycle_for(name), "category"


SOURCE_LABEL = {
    "manual": "ви вказали самі",
    "observed": "з ваших чеків",
    "category": "оцінка за категорією",
}


def build(items: list[dict[str, Any]], stored: dict[str, dict[str, Any]],
          today: date | None = None) -> dict[str, Any]:
    """Зводить позиції плану з тим, що гість уже налаштував.

    `items`  — позиції плану (у detail.history лежать реальні дати покупок)
    `stored` — рядки product_cycles за слагом
    """
    today = today or date.today()
    rows: list[dict[str, Any]] = []

    for item in items:
        if item.get("action") == "blocked":
            continue
        slug = item.get("slug")
        if not slug:
            continue
        saved = stored.get(slug) or {}
        history = (item.get("detail") or {}).get("history") or []
        cycle, source = cycle_for(item.get("name") or "", history, saved.get("cycle_override"))

        dates = sorted({h.get("date") for h in history if h.get("date")})
        last_bought = date.fromisoformat(dates[-1]) if dates else None
        next_due = last_bought + timedelta(days=cycle) if last_bought else None
        due_in = (next_due - today).days if next_due else None

        rows.append({
            "slug": slug,
            "product_id": item.get("product_id"),
            "name": item.get("name"),
            "image": item.get("image"),
            "price": item.get("price"),
            "quantity": item.get("quantity", 1),
            "cycle_days": cycle,
            "cycle_source": source,
            "cycle_source_label": SOURCE_LABEL[source],
            "purchases": len(dates),
            "last_bought": last_bought.isoformat() if last_bought else None,
            "next_due": next_due.isoformat() if next_due else None,
            "due_in_days": due_in,
            "overdue": due_in is not None and due_in < 0,
            "due": due_in is not None and due_in <= DUE_HORIZON_DAYS,
            "reminder_on": bool(saved.get("reminder_on")),
        })

    rows.sort(key=lambda r: (r["due_in_days"] is None, r["due_in_days"]))
    due = [r for r in rows if r["due"]]
    return {
        "has_data": True,
        "due": due,
        "upcoming": [r for r in rows if not r["due"] and r["due_in_days"] is not None][:8],
        "all": rows,
        "summary": {
            "due_count": len(due),
            "due_total": round(sum((r["price"] or 0) * r["quantity"] for r in due), 2),
            "reminders_on": sum(1 for r in rows if r["reminder_on"]),
            "observed": sum(1 for r in rows if r["cycle_source"] == "observed"),
        },
    }


def digest_line(row: dict[str, Any]) -> str:
    """Рядок для дайджесту в бота."""
    if row["overdue"]:
        return f"• {row['name']} — мало закінчитись {abs(row['due_in_days'])} дн. тому"
    if row["due_in_days"] == 0:
        return f"• {row['name']} — за розрахунком закінчується сьогодні"
    return f"• {row['name']} — приблизно через {row['due_in_days']} дн."


def accuracy(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Наскільки цикл справдився на історії гостя.

    Для кожної покупки, крім першої, передбачаємо дату з попередньої плюс цикл
    і міряємо помилку в днях. Це пряма відповідь на «а ви точно вгадуєте ритм?»
    — без неї цифра циклу нічим не підкріплена.
    """
    errors: list[int] = []
    checked = 0
    for item in items:
        history = (item.get("detail") or {}).get("history") or []
        dates = sorted({h.get("date") for h in history if h.get("date")})
        if len(dates) < MIN_PURCHASES_FOR_OBSERVED:
            continue
        parsed = [date.fromisoformat(d) for d in dates]
        cycle, _source = cycle_for(item.get("name") or "", history)
        checked += 1
        for previous, actual in zip(parsed, parsed[1:]):
            predicted = previous + timedelta(days=cycle)
            errors.append(abs((actual - predicted).days))
    if not errors:
        return {"measurable": False, "products": 0, "reason": "замало повторних покупок"}
    return {
        "measurable": True,
        "products": checked,
        "points": len(errors),
        "mean_error_days": round(sum(errors) / len(errors), 1),
        "within_3_days_pct": round(sum(1 for e in errors if e <= 3) / len(errors) * 100),
    }
