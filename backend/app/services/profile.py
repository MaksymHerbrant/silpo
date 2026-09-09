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

from datetime import date
from typing import Any

from app.mcp import tools as T
from app.nutrition import allergens as al
from app.nutrition.targets import age_from_birthday


async def load(api) -> dict[str, Any]:
    """Збирає профіль гостя з трьох tools MCP. Помилка окремого не критична."""
    profile: dict[str, Any] = {}
    restrictions: list[al.Restriction] = []
    family: dict[str, Any] = {}

    try:
        payload = await api.call(T.GET_MY_PROFILE, {})
        if not T.is_mcp_error(payload) and isinstance(payload, dict):
            profile = payload.get("profile") or {}
    except Exception:  # noqa: BLE001
        pass

    try:
        payload = await api.call(T.GET_FOOD_RESTRICTIONS, {})
        if not T.restrictions_are_empty(payload):
            restrictions = al.parse_restrictions(payload)
    except Exception:  # noqa: BLE001
        pass

    try:
        payload = await api.call(T.GET_MY_FAMILY, {})
        if not T.is_mcp_error(payload) and isinstance(payload, dict):
            family = {
                "children": len(payload.get("children") or []),
                "pets": len(payload.get("pets") or []),
                "members": len(payload.get("members") or []),
            }
    except Exception:  # noqa: BLE001
        pass

    birthday = profile.get("birthday")
    return {
        "name": profile.get("firstName"),
        "age": age_from_birthday(birthday) if birthday else None,
        "gender": profile.get("gender"),
        "restrictions": [
            {"slug": r.slug, "label": r.label, "triggers": list(r.triggers)}
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
