"""Можливості — те, заради чого гість відкриває застосунок.

Це не нова бізнес-логіка: усі знахідки вже пораховані в plan.py. Тут вони
перетворюються на ОДИН ранжований список із грошима нагорі, щоб головний
екран за десять секунд відповідав на питання «що ти для мене знайшов?».

Порядок навмисний: спершу гроші (акції на звичне, дешевші аналоги), далі
безпека, далі одне спостереження про харчування, і лише потім спостереження
про звички. Аналітика — це доказ, а не продукт.
"""
from __future__ import annotations

from typing import Any

# kind знахідки -> як подати можливість
SHAPE: dict[str, dict[str, Any]] = {
    "promo":       {"icon": "💰", "rank": 0, "money": True,
                    "title": "{n} звичних товари зараз в акції"},
    "brand":       {"icon": "🔁", "rank": 1, "money": True,
                    "title": "{n} види, де марка вам не принципова"},
    "alternative": {"icon": "🔄", "rank": 2, "money": True,
                    "title": "{n} реалістичні дешевші аналоги"},
    "safety":      {"icon": "⛔", "rank": 3, "money": False,
                    "title": "{n} позиції конфліктують з вашим профілем"},
    "preference":  {"icon": "🎯", "rank": 4, "money": False,
                    "title": "{n} позиції під ваші вподобання"},
    "health":      {"icon": "🥗", "rank": 5, "money": False,
                    "title": "Одна проста зміна на краще"},
    "fading":      {"icon": "🕰️", "rank": 6, "money": False,
                    "title": "{n} позиції випали зі звички"},
    "emerging":    {"icon": "🌱", "rank": 7, "money": False,
                    "title": "{n} нових товари у вашому кошику"},
    "threshold":   {"icon": "💸", "rank": 8, "money": False,
                    "title": "{n} варіанти приховано ціновим порогом"},
}

# Шум і механіка на головний екран не виносяться
HIDDEN = {"noise", "usual"}


def _saving_for(kind: str, items: list[dict[str, Any]]) -> float:
    """Скільки гривень стоїть за цією можливістю. Рахується з фактів."""
    if kind == "promo":
        return sum(
            float(i.get("saved") or 0) * int(i.get("quantity") or 1)
            for i in items if i.get("on_promotion")
        )
    total = 0.0
    for item in items:
        alt = item.get("alternative") or {}
        saved = float(alt.get("saved") or 0)
        if saved > 0:
            total += saved * int(item.get("quantity") or 1)
    return total


def build(plan: dict[str, Any]) -> dict[str, Any]:
    """Ранжований список можливостей + підсумок грошима."""
    items_by_slug = {i.get("slug"): i for i in (plan.get("items") or [])}
    out: list[dict[str, Any]] = []

    for finding in plan.get("findings") or []:
        kind = finding.get("kind")
        if kind in HIDDEN:
            continue
        shape = SHAPE.get(kind)
        if shape is None:
            continue

        slugs = finding.get("slugs") or []
        related = [items_by_slug[s] for s in slugs if s in items_by_slug]
        count = len(slugs) or len(related)
        saving = round(_saving_for(kind, related), 2) if shape["money"] else 0.0

        out.append({
            "kind": kind,
            "icon": shape["icon"],
            "title": shape["title"].format(n=count),
            "detail": finding.get("detail") or "",
            "saving": saving,
            "count": count,
            "slugs": slugs,
            "is_money": shape["money"],
            "_rank": shape["rank"],
        })

    out.sort(key=lambda o: (o["_rank"], -o["saving"]))
    for row in out:
        row.pop("_rank", None)

    summary = plan.get("summary") or {}
    basket = [i for i in (plan.get("items") or []) if i.get("action") != "blocked"]
    return {
        "items": out,
        "count": len(out),
        "total_saving": round(sum(o["saving"] for o in out), 2),
        "basket": {
            "count": len(basket),
            "total": summary.get("total_price"),
            "weekly": summary.get("weekly_price"),
        },
    }


def evidence_for(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Факти, на яких тримається рекомендація. Жодних міркувань моделі.

    Це свідома заміна «ходу думки»: гостю потрібні не токени роздумів, а
    перевірювані підстави — скільки днів купував, за скільки тижнів, яка
    ціна зараз і яка в альтернативи.
    """
    habit = item.get("habit") or {}
    alt = item.get("alternative") or {}
    rows: list[dict[str, Any]] = []

    def add(label: str, value: Any, unit: str = "") -> None:
        if value not in (None, "", 0):
            rows.append({"label": label, "value": value, "unit": unit})

    add("Купували в різні дні", habit.get("days"))
    add("Різних тижнів", habit.get("weeks"))
    if item.get("cycle_days"):
        add("Середній інтервал", item["cycle_days"], "дн.")
    if habit.get("since_last_days") is not None:
        add("Востаннє", habit.get("since_last_days"), "дн. тому")
    if (item.get("kind_brands") or 1) > 1:
        add("Різних марок брали", item.get("kind_brands"))
        loyalty = item.get("loyalty")
        if loyalty is not None:
            rows.append({
                "label": "Вірність марці",
                "value": "марка не принципова" if item.get("brand_indifferent")
                         else f"{round(loyalty * 100)}%",
                "unit": "",
            })
    add("Ціна зараз", item.get("price"), "₴")
    if item.get("on_promotion") and item.get("old_price"):
        add("Була ціна", item.get("old_price"), "₴")
    if alt:
        add("Ціна альтернативи", alt.get("price"), "₴")
        if (alt.get("saved") or 0) > 0:
            add("Економія", round(alt["saved"] * int(item.get("quantity") or 1)), "₴")
    rows.append({
        "label": "Акція зараз",
        "value": "так" if item.get("on_promotion") else "ні",
        "unit": "",
    })
    return rows
