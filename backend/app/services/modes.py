"""Режим гостя: що виносити вгору і що вмикати заздалегідь.

Режим НЕ змінює того, що ми рахуємо — рахунок завжди однаковий. Він змінює
подачу: порядок стрічки, що позначено заздалегідь, наскільки розгорнуті
деталі харчування й як часто ми пишемо в бота.

Це свідомо вузький вплив. Режим, який міняє самі числа, довелося б окремо
пояснювати: «чому в економії бал інший?».
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

AUTO, SAVING, HEALTH, ANALYTICS = "auto", "saving", "health", "analytics"


@dataclass
class Mode:
    key: str
    label: str
    # Порядок знахідок у стрічці. Те, чого немає у списку, йде після.
    feed: tuple[str, ...]
    # Які дії позначені галочкою при відкритті плану
    preselect: frozenset[str]
    # 0 — лише бал, 1 — плюс перекоси, 2 — плюс БЖВ і тарілка одразу
    nutrition_depth: int = 1
    # Чи дозволяємо агенту переставляти стрічку по-своєму
    agent_may_reorder: bool = False
    notes: str = ""


MODES: dict[str, Mode] = {
    AUTO: Mode(
        AUTO, "Просто оптимізуй за мене",
        feed=("safety", "promo", "health", "preference", "alternative", "emerging", "fading"),
        preselect=frozenset({"keep", "add", "switch", "review"}),
        nutrition_depth=0,
        agent_may_reorder=True,
        notes="Агент сам вирішує порядок і позначає все безпечне в межах порогу",
    ),
    SAVING: Mode(
        SAVING, "Економія",
        feed=("promo", "alternative", "threshold", "safety", "health", "emerging", "fading"),
        preselect=frozenset({"add", "review", "switch"}),
        nutrition_depth=0,
        notes="Спершу гроші: акції на звичне і вигідніші аналоги",
    ),
    HEALTH: Mode(
        HEALTH, "Здоровіше",
        feed=("health", "safety", "preference", "promo", "alternative", "emerging", "fading"),
        preselect=frozenset({"switch"}),
        nutrition_depth=2,
        notes="Спершу одна конкретна зміна, деталі харчування розгорнуті",
    ),
    ANALYTICS: Mode(
        ANALYTICS, "Аналітика",
        feed=("emerging", "fading", "noise", "threshold", "safety", "promo", "health", "alternative"),
        preselect=frozenset(),
        nutrition_depth=2,
        notes="Нічого не вмикається саме — ви обираєте",
    ),
}


def get(key: str | None) -> Mode:
    return MODES.get(key or AUTO, MODES[AUTO])


def apply(plan: dict[str, Any], key: str | None) -> None:
    """Переставляє стрічку й розставляє галочки під режим гостя."""
    mode = get(key)

    rank = {kind: i for i, kind in enumerate(mode.feed)}
    plan["findings"] = sorted(
        plan.get("findings") or [],
        key=lambda f: rank.get(f.get("kind"), len(rank)),
    )

    for item in plan.get("items") or []:
        if item.get("action") == "blocked":
            item["selected"] = False
            continue
        item["selected"] = item.get("action") in mode.preselect

    summary = plan.setdefault("summary", {})
    summary["mode"] = mode.key
    summary["mode_label"] = mode.label
    summary["mode_note"] = mode.notes
    summary["nutrition_depth"] = mode.nutrition_depth
    summary["preselected"] = sum(1 for i in plan.get("items") or [] if i.get("selected"))
