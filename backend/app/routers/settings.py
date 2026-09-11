"""Налаштування агента: режим і ціновий поріг.

Ціновий поріг — найважливіше налаштування продукту: за опитуванням ціна є
критерієм вибору №1 (62%). Зміна порогу робить попередній план недійсним,
тому кеш скидається одразу — інакше гість змінює межу й бачить старі
пропозиції, які їй не відповідають.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db import repo
from app.security.session import current_user_id
from app.services import jobs, modes as app_modes, pricing

router = APIRouter(tags=["settings"])

MODES: tuple[dict[str, str], ...] = (
    {
        "key": "auto", "label": "Просто оптимізуй за мене",
        "hint": "Агент сам балансує ціну і звичку. Мінімум сповіщень",
    },
    {
        "key": "saving", "label": "Економія",
        "hint": "Спершу акції на звичне і вигідніші аналоги",
    },
    {
        "key": "health", "label": "Здоровіше",
        "hint": "Одна конкретна зміна на краще, без моралі",
    },
    {
        "key": "analytics", "label": "Аналітика",
        "hint": "Витрати, звички і ядро кошика. Нічого не вмикається саме",
    },
)

DEFAULT_MODE = "auto"
_MODE_KEYS = {m["key"] for m in MODES}

# Кеші, які залежать від налаштувань і мають померти разом зі зміною
DEPENDENT_JOBS = ("plan_next", "insights", "usual")


class SettingsIn(BaseModel):
    mode: str | None = None
    # Приймаємо і 0.05, і 5, і "5%", і "any" — нормалізує pricing.normalize
    price_tolerance: Any | None = None
    unlimited_price: bool = False
    restriction_strictness: dict[str, str] | None = None
    # Онбординг пройдено (у тому числі пропущено — пропуск теж є відповіддю)
    onboarded: bool = False


def _view(row: dict[str, Any]) -> dict[str, Any]:
    tolerance = row.get("price_tolerance", pricing.DEFAULT_TOLERANCE)
    normalized = pricing.normalize(tolerance)
    return {
        "mode": row.get("mode") or DEFAULT_MODE,
        "price_tolerance": normalized,
        "price_tolerance_key": pricing.option_key(tolerance),
        "price_tolerance_label": pricing.describe(tolerance),
        "restriction_strictness": row.get("restriction_strictness") or {},
        "mode_note": app_modes.get(row.get("mode")).notes,
        # Онбординг показуємо лише тому, хто його ще не бачив
        "onboarded": bool(row.get("onboarded_at")),
        "options": {
            "modes": list(MODES),
            "price_tolerance": list(pricing.OPTIONS),
        },
    }


@router.get("/settings")
async def get_settings(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    # get_prefs віддає лише наявні ключі, тож _view коректно розрізняє
    # «не налаштовував» (ключа немає → дефолт) і «без обмежень» (None).
    return _view(await repo.get_prefs(user_id))


@router.put("/settings")
async def put_settings(
    payload: SettingsIn, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    values: dict[str, Any] = {}

    if payload.mode and payload.mode in _MODE_KEYS:
        values["mode"] = payload.mode

    if payload.unlimited_price:
        values["price_tolerance"] = None
    elif payload.price_tolerance is not None:
        values["price_tolerance"] = pricing.normalize(payload.price_tolerance)

    if payload.restriction_strictness is not None:
        values["restriction_strictness"] = {
            slug: level
            for slug, level in payload.restriction_strictness.items()
            if level in {"block", "warn"}
        }

    if payload.onboarded:
        values["onboarded_at"] = datetime.now(UTC).isoformat()

    row = await repo.save_prefs(user_id, values)

    # План побудований під старий поріг більше не дійсний
    if "price_tolerance" in values or "mode" in values:
        for name in DEPENDENT_JOBS:
            jobs.invalidate(name, user_id)
            jobs.reset_failures(name, user_id)

    return {**_view(row), "saved": True}
