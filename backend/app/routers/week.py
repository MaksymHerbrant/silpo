from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.security.session import current_user_id
from app.services import goals, week

router = APIRouter(tags=["week"])


class GoalIn(BaseModel):
    goal: str = "health"
    weight_kg: float | None = None
    height_cm: float | None = None
    activity: str = "moderate"
    household_size: int = 1
    weekly_budget: float | None = None


@router.get("/goals")
async def get_goals(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    return await goals.get_state(user_id)


@router.post("/goals")
async def set_goals(payload: GoalIn, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    return await goals.save(user_id, payload.model_dump())


@router.get("/week/overview")
async def overview(
    refresh: bool = False, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    """Норми проти реальних покупок. Перший виклик ставить задачу у фон."""
    return await week.overview(user_id, refresh)


@router.get("/week/plan")
async def plan_status(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Статус і результат останньої збірки кошика."""
    return await week.plan_status(user_id)


class PlanIn(BaseModel):
    budget: float | None = None
    household: int | None = None
    # Вільний текст: «без риби», «щоб було що брати на роботу», «швидко готувати»
    preferences: str | None = None
    prefer_promo: bool = True


@router.post("/week/plan")
async def build_plan(
    params: PlanIn | None = None, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    """Зібрати кошик на тиждень під ціль, бюджет і побажання гостя."""
    params = params or PlanIn()
    return await week.build_plan(
        user_id, params.budget, params.preferences, params.household, params.prefer_promo
    )


@router.post("/week/plan/{plan_id}/apply")
async def apply_plan(plan_id: str, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    try:
        return await week.apply_plan(user_id, plan_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
