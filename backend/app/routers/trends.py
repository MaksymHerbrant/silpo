from __future__ import annotations

from fastapi import APIRouter, Depends

from app.security.session import current_user_id
from app.services import trends

router = APIRouter(tags=["trends"])


@router.get("/trends/weekly")
async def weekly(refresh: bool = False, user_id: str = Depends(current_user_id)) -> dict:
    """Тижневий тренд + звички з офлайн-чеків. За замовчуванням — з кешу."""
    return await trends.weekly_trend(user_id, refresh=refresh)


@router.post("/trends/rebuild")
async def rebuild(user_id: str = Depends(current_user_id)) -> dict:
    """Запускає перерахунок профілю У ФОНІ й одразу відповідає.

    Сам перерахунок триває до хвилини (десятки викликів MCP), а HTTP-запит
    такої довжини рвався тунелем із 502. Клієнт опитує GET /trends/weekly,
    поки там building=true.
    """
    return await trends.start_rebuild(user_id)
