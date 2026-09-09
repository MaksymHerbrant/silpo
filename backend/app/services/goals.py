"""Ціль гостя і персональні норми.

Стать і дату народження беремо з профілю Сільпо (silpo_get_my_profile) —
питати те, що вже є в системі, погана ідея. Решту (ціль, вага, зріст,
активність) питаємо одним екраном.
"""
from __future__ import annotations

from typing import Any

from app.db import repo
from app.mcp import tools as T
from app.mcp.gateway import silpo
from app.nutrition.targets import GOALS, Targets, compute_targets


async def fetch_silpo_profile(user_id: str) -> dict[str, Any]:
    """Стать і дата народження з профілю Сільпо. Помилка не критична."""
    try:
        async with silpo(user_id) as api:
            payload = await api.call(T.GET_MY_PROFILE, {})
    except Exception:  # noqa: BLE001
        return {}
    if T.is_mcp_error(payload) or not isinstance(payload, dict):
        return {}
    profile = payload.get("profile") or {}
    return {
        "sex": profile.get("gender"),
        "birthday": profile.get("birthday"),
        "first_name": profile.get("firstName"),
    }


def targets_from_row(row: dict[str, Any] | None) -> Targets:
    row = row or {}
    return compute_targets(
        goal=row.get("goal") or "health",
        weight_kg=float(row["weight_kg"]) if row.get("weight_kg") else None,
        height_cm=float(row["height_cm"]) if row.get("height_cm") else None,
        activity=row.get("activity") or "moderate",
        sex=row.get("sex"),
        birthday=row.get("birthday"),
    )


async def get_state(user_id: str) -> dict[str, Any]:
    row = await repo.get_goal(user_id)
    targets = targets_from_row(row)
    return {
        "configured": bool(row and row.get("goal")),
        "goal": row or {},
        "targets": targets.as_dict(),
        "options": {
            "goals": [{"key": k, "label": v["label"]} for k, v in GOALS.items()],
            "activity": [
                {"key": "sedentary", "label": "Сидяча робота, без спорту"},
                {"key": "light", "label": "1–2 тренування на тиждень"},
                {"key": "moderate", "label": "3–4 тренування"},
                {"key": "high", "label": "5–6 тренувань"},
                {"key": "athlete", "label": "Щодня або фізична робота"},
            ],
        },
    }


async def save(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    profile = await fetch_silpo_profile(user_id)
    values = {
        "goal": payload.get("goal") or "health",
        "weight_kg": payload.get("weight_kg"),
        "height_cm": payload.get("height_cm"),
        "activity": payload.get("activity") or "moderate",
        "household_size": int(payload.get("household_size") or 1),
        "weekly_budget": payload.get("weekly_budget"),
        "sex": profile.get("sex"),
        "birthday": profile.get("birthday"),
    }
    targets = compute_targets(
        goal=values["goal"], weight_kg=values["weight_kg"], height_cm=values["height_cm"],
        activity=values["activity"], sex=values["sex"], birthday=values["birthday"],
    )
    values.update({
        "target_kcal": targets.kcal, "target_protein": targets.protein,
        "target_fat": targets.fat, "target_carbs": targets.carbs,
    })
    await repo.save_goal(user_id, values)
    return {"goal": values, "targets": targets.as_dict(), "profile": profile}
