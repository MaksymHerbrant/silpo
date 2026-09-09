from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import repo
from app.security.session import current_user_id
from app.services import jobs, swaps

router = APIRouter(tags=["swaps"])


@router.get("/swaps/suggestions")
async def suggestions(
    rebuild: bool = True,
    source: str = "habits",           # habits | cart | both
    user_id: str = Depends(current_user_id),
) -> dict:
    if rebuild:
        cached = jobs.get_cached("swaps", user_id)
        if cached is None:
            await jobs.start(
                "swaps", user_id, lambda: swaps.build_suggestions(user_id, source=source)
            )
            return {
                "suggestions": await repo.list_swap_suggestions(user_id),
                "building": True,
                "stats": await repo.swap_acceptance_stats(user_id),
            }
        items = cached
    else:
        items = await repo.list_swap_suggestions(user_id)
    pending = [s for s in items if s.get("accepted") is None]
    return {
        "suggestions": pending or items,
        "building": jobs.is_running("swaps", user_id),
        "stats": await repo.swap_acceptance_stats(user_id),
    }


@router.post("/swaps/{swap_id}/apply")
async def apply(swap_id: str, user_id: str = Depends(current_user_id)) -> dict:
    try:
        return await swaps.apply_swap(user_id, swap_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/swaps/{swap_id}/decline")
async def decline(swap_id: str, user_id: str = Depends(current_user_id)) -> dict:
    try:
        await swaps.decline_swap(user_id, swap_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"declined": True}
