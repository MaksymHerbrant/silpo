"""Нагадування про поповнення і стеження за цінами.

Обидва спираються на вже побудований план — свого читання чеків не роблять.
Тому відповідають миттєво, поки план у кеші.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import repo
from app.security.session import current_user_id
from app.services import cycles, digest, pipeline, price_watch

router = APIRouter(tags=["reminders"])


class ReminderIn(BaseModel):
    enabled: bool | None = None
    cycle_days: int | None = None


@router.get("/reminders")
async def get_reminders(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    plan = await pipeline.cached_plan_async(user_id)
    if not plan or plan.get("building"):
        return {"building": True, "has_data": False}
    if not plan.get("has_data"):
        return {"has_data": False, "reason": plan.get("reason")}

    stored = await repo.cycles_for(user_id)
    return cycles.build(plan.get("items") or [], stored)


@router.put("/reminders/{slug}")
async def set_reminder(
    slug: str, payload: ReminderIn, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if payload.enabled is not None:
        values["reminder_on"] = payload.enabled
    if payload.cycle_days is not None:
        if not cycles.MIN_CYCLE_DAYS <= payload.cycle_days <= cycles.MAX_CYCLE_DAYS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Цикл має бути від {cycles.MIN_CYCLE_DAYS} до {cycles.MAX_CYCLE_DAYS} днів",
            )
        values["cycle_override"] = payload.cycle_days
    if not values:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нема що змінювати")

    plan = await pipeline.cached_plan_async(user_id) or {}
    item = next((i for i in (plan.get("items") or []) if i.get("slug") == slug), None)
    if item is not None:
        values["name"] = item.get("name")

    await repo.save_cycle(user_id, slug, values)
    stored = await repo.cycles_for(user_id)
    return cycles.build(plan.get("items") or [], stored)


@router.get("/price-drops")
async def price_drops(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Порівнює поточні ціни з попереднім знімком і одразу оновлює знімок."""
    plan = await pipeline.cached_plan_async(user_id)
    if not plan or plan.get("building"):
        return {"building": True, "drops": []}
    if not plan.get("has_data"):
        return {"drops": [], "reason": plan.get("reason")}

    stored = await repo.price_snapshot(user_id)
    result = price_watch.compare(plan.get("items") or [], stored)
    await repo.save_price_snapshot(user_id, result["snapshot"])
    return {
        "drops": result["drops"],
        "tracked": result["tracked"],
        "total_saved": result["total_saved"],
        "first_run": not stored,
    }


@router.post("/reminders/digest")
async def send_digest(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Надсилає дайджест собі — щоб побачити, як він виглядає, не чекаючи ночі."""
    return await digest.send_to_user(user_id, force=True, preview=True)
