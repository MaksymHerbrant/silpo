"""API агента: запуск, статус, застосування зібраного кошика."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.agent import runner
from app.db import repo
from app.mcp import tools as T
from app.mcp.gateway import silpo
from app.nutrition.categories import GOAL_FOCUS
from app.security.session import current_user_id
from app.services import goals, jobs
from app.services.cart_analysis import fetch_cart

router = APIRouter(tags=["agent"])

DEFAULT_PROMPT = (
    "Збери мені кошик на тиждень під мою ціль і бюджет. "
    "Спирайся на те, що я зазвичай купую, і врахуй акції."
)


class RunIn(BaseModel):
    prompt: str | None = None


async def _profile(user_id: str) -> dict[str, Any]:
    row = await repo.get_goal(user_id) or {}
    restrictions: list[str] = []
    try:
        async with silpo(user_id) as api:
            payload = await api.call(T.GET_FOOD_RESTRICTIONS, {})
        if not T.restrictions_are_empty(payload):
            from app.nutrition import allergens as al

            restrictions = [r.label for r in al.parse_restrictions(payload)]
    except Exception:  # noqa: BLE001
        pass

    goal_key = row.get("goal") or "healthier"
    focus = GOAL_FOCUS.get(goal_key, GOAL_FOCUS["healthier"])
    return {
        "goal": goal_key,
        "goal_label": focus["label"],
        "goal_hint": focus["hint"],
        "restrictions": restrictions,
        "weekly_budget": float(row["weekly_budget"]) if row.get("weekly_budget") else None,
        "household_size": int(row.get("household_size") or 1),
        "preferences": row.get("preferences"),
    }


@router.get("/agent/context")
async def context(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Факти для стартового екрана: скільки чеків, витрати, економія.

    Свідомо не показуємо «потенційну економію» — реальна відома лише після
    того, як агент зібрав кошик, і вигадувати її не можна.
    """
    profile = await _profile(user_id)
    cached = jobs.get_cached("agent_context", user_id)
    if cached is not None:
        return {**cached, "profile": profile}

    async def _factory() -> dict[str, Any]:
        from app.nutrition import categories as cats
        from app.services.habits import fetch_offline_orders

        async with silpo(user_id) as api:
            ctx, _c, _m = await fetch_cart(api)
            if ctx is None:
                return {"stats": None}
            orders = await fetch_offline_orders(api, ctx)

        if not orders:
            return {"stats": None}
        lines = [line for order in orders for line in order.items]
        structure = cats.analyse(lines, profile.get("goal"))
        problem = next((c for c in structure.categories if c.status == "above"), None)
        days = max((orders[0].created_at - orders[-1].created_at).days, 1) if len(orders) > 1 else 1
        return {
            "stats": {
                "receipts": len(orders),
                "period_days": days,
                "total_spend": round(sum(o.total for o in orders), 2),
                "saved": round(sum(o.discount for o in orders), 2),
                "top_category": (
                    {"label": problem.label, "share": problem.share} if problem else None
                ),
            }
        }

    result = await jobs.cached_or_start("agent_context", user_id, _factory)
    return {**result, "profile": profile}


@router.post("/agent/run")
async def run_agent(
    params: RunIn | None = None, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    """Запускає агента у фоні: він сам вирішує, які tools викликати."""
    params = params or RunIn()
    prompt = params.prompt or DEFAULT_PROMPT
    profile = await _profile(user_id)

    jobs.invalidate("agent", user_id)
    runner.reset_progress(user_id)

    async def _factory() -> dict[str, Any]:
        result = await runner.run(user_id, prompt, profile)
        return result.as_dict()

    started = await jobs.start("agent", user_id, _factory)
    return {**started, "prompt": prompt, "profile": profile}


@router.get("/agent/run")
async def agent_status(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Статус і результат останнього запуску агента."""
    cached = jobs.get_cached("agent", user_id)
    if cached is not None:
        return {**cached, "building": jobs.is_running("agent", user_id)}
    # Поки агент працює — віддаємо кроки, які вже виконано
    return {
        "building": jobs.is_running("agent", user_id),
        "error": jobs.last_error("agent", user_id),
        "steps": runner.live_steps(user_id),
        "draft": [], "summary": {},
    }


@router.post("/agent/apply")
async def apply_draft(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Записує зібраний агентом кошик у Сільпо. Тільки після дії гостя."""
    cached = jobs.get_cached("agent", user_id)
    draft = (cached or {}).get("draft") or []
    if not draft:
        raise HTTPException(status.HTTP_409_CONFLICT, "Немає зібраного кошика")

    products = [
        {"productId": item["product_id"], "quantity": item.get("quantity", 1)}
        for item in draft if item.get("product_id")
    ]
    if not products:
        raise HTTPException(status.HTTP_409_CONFLICT, "У кошику немає товарів із коректним id")

    async with silpo(user_id) as api:
        ctx, _cart, _meta = await fetch_cart(api)
        if ctx is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Кошик Сільпо недоступний")
        result = await api.call(T.ADD_OR_UPDATE_CART, {
            "shoppingCartId": ctx.cart_id,
            "products": [
                {**p, "companyId": ctx.company_id, "branchId": ctx.branch_id} for p in products
            ],
        })
        # Перечитуємо кошик — доказ, що запис справді відбувся
        _c, after, _m = await fetch_cart(api)

    return {
        "applied": True,
        "added": len(products),
        "cart_id": ctx.cart_id,
        "cart_now": [{"name": p.get("name"), "quantity": p.get("quantity")} for p in after],
        "mcp_result": result,
    }


@router.get("/agent/shopping-list")
async def shopping_list(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Офлайн-варіант: категоризований список для магазину."""
    cached = jobs.get_cached("agent", user_id)
    draft = (cached or {}).get("draft") or []
    if not draft:
        raise HTTPException(status.HTTP_409_CONFLICT, "Немає зібраного кошика")

    from app.nutrition.categories import CATEGORY_LABELS

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in draft:
        grouped.setdefault(item.get("category", "other"), []).append({
            "name": item["name"], "quantity": item.get("quantity", 1),
            "price": item.get("price"), "on_promotion": item.get("on_promotion"),
        })
    return {
        "groups": [
            {"category": key, "label": CATEGORY_LABELS.get(key, key), "items": items}
            for key, items in grouped.items()
        ],
        "summary": (cached or {}).get("summary", {}),
    }
