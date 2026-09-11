"""Метрика цінності продукту.

Відповідає на питання, яке журі поставить першим: «звідки ви знаєте, що це
комусь потрібно?» Не «користувач подивився графік», а:
  * скільки пропозицій показано і скільки прийнято;
  * скільки гривень з прийнятого — за цінами НА МОМЕНТ ПОКАЗУ;
  * скільки позицій зібрано автоматично;
  * наскільки точно вгадано ритм покупок.

Свідомо НЕ рахуємо «зекономлені хвилини»: ми їх не вимірювали, і вигадувати
таку цифру означало б підірвати довіру до решти.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import repo
from app.security.session import current_user_id
from app.services import cycles, decisions, pipeline

router = APIRouter(tags=["metrics"])


class DecisionIn(BaseModel):
    accepted: bool


@router.get("/metrics")
async def get_metrics(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    rows = await repo.all_decisions(user_id)
    proposals = decisions.stats(rows)

    plan = await pipeline.cached_plan_async(user_id) or {}
    summary = plan.get("summary") or {}
    items = plan.get("items") or []

    return {
        "proposals": proposals,
        "core_basket": {
            "positions": summary.get("items"),
            "weekly_price": summary.get("weekly_price"),
            "periodic_price": summary.get("periodic_price"),
            "filtered_count": summary.get("filtered_count"),
            "filtered_spend": summary.get("filtered_spend"),
            "receipts": summary.get("receipts"),
            "weeks": summary.get("based_on_weeks"),
        },
        "cycles": cycles.accuracy(items),
        "disclaimer": (
            "Економія рахується за цінами на момент показу пропозиції. "
            "Час ми не вимірюємо і не оцінюємо."
        ),
    }


@router.post("/decisions/{decision_id}")
async def decide(
    decision_id: str, payload: DecisionIn, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    row = await repo.get_decision(user_id, decision_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пропозицію не знайдено")
    if row.get("accepted") is not None:
        return {"already_decided": True, "accepted": row["accepted"]}
    await repo.decide(decision_id, payload.accepted)
    return {"accepted": payload.accepted}
