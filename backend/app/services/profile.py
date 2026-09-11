"""Профіль гостя — єдине джерело правди про обмеження.

Критичний принцип безпеки: AI НЕ вигадує алергії й дієтичні обмеження.
Вони приходять із профілю Сільпо, який гість заповнював сам у застосунку:

    silpo_get_my_profile          -> ім'я, стать, дата народження
    silpo_get_my_food_restrictions -> слаги обмежень (lactoza, gluten, sugar…)
    silpo_get_my_family            -> діти й улюбленці, якщо є

Якщо профіль порожній — ми чесно кажемо «обмеження не вказані» і нічого не
блокуємо, замість того щоб вгадувати.
"""
from __future__ import annotations

import asyncio

from datetime import date
from typing import Any

from app.mcp import tools as T
from app.nutrition import allergens as al
from app.nutrition.targets import age_from_birthday


async def load(api) -> dict[str, Any]:
    """Збирає профіль гостя з трьох tools MCP — одним заходом, не по черзі.

    Виклики незалежні: ім'я, обмеження й склад родини ніяк не пов'язані.
    Помилка окремого не критична — просто та частина лишається порожньою.
    """
    profile: dict[str, Any] = {}
    restrictions: list[al.Restriction] = []
    family: dict[str, Any] = {}

    raw_profile, raw_restrictions, raw_family = await asyncio.gather(
        api.call(T.GET_MY_PROFILE, {}),
        api.call(T.GET_FOOD_RESTRICTIONS, {}),
        api.call(T.GET_MY_FAMILY, {}),
        return_exceptions=True,
    )

    if not isinstance(raw_profile, BaseException) and not T.is_mcp_error(raw_profile):
        if isinstance(raw_profile, dict):
            profile = raw_profile.get("profile") or {}

    if not isinstance(raw_restrictions, BaseException):
        if not T.restrictions_are_empty(raw_restrictions):
            restrictions = al.parse_restrictions(raw_restrictions)

    if not isinstance(raw_family, BaseException) and not T.is_mcp_error(raw_family):
        if isinstance(raw_family, dict):
            family = {
                "children": len(raw_family.get("children") or []),
                "pets": len(raw_family.get("pets") or []),
                "members": len(raw_family.get("members") or []),
            }

    birthday = profile.get("birthday")
    return {
        "name": profile.get("firstName"),
        "age": age_from_birthday(birthday) if birthday else None,
        "gender": profile.get("gender"),
        "restrictions": [
            {
                "slug": r.slug, "label": r.label, "triggers": list(r.triggers),
                # allergen блокує завжди; preference лише пропонує заміну —
                # і лише в категоріях, де обмеження є суттю продукту
                "kind": r.kind,
            }
            for r in restrictions
        ],
        "restriction_objects": restrictions,     # для внутрішнього використання
        "has_restrictions": bool(restrictions),
        "family": family,
        "source": "Профіль Сільпо",
    }


def status_line(profile: dict[str, Any]) -> dict[str, Any]:
    """Рядок статусу для головного екрана: що саме враховано."""
    restrictions = profile.get("restrictions") or []
    if restrictions:
        labels = ", ".join(r["label"] for r in restrictions)
        return {
            "active": True,
            "title": f"Обмеження враховано: {labels.lower()}",
            "detail": "Позиції зі складом, що конфліктує з профілем, блокуються автоматично",
        }
    return {
        "active": False,
        "title": "Обмеження в профілі не вказані",
        "detail": "Заповніть анкету в застосунку Сільпо — і ми перевірятимемо склад кожного товару",
    }
