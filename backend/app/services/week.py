"""Тижневий план: дефіцити + зібраний кошик + застосування в Сільпо."""
from __future__ import annotations

from typing import Any

from app.db import repo
from app.mcp import tools as T
from app.mcp.gateway import silpo
from app.nutrition import allergens as al
from app.nutrition.targets import Gap, compare, gap_to_food
from app.services import goals, habits, jobs, planner
from app.services.cart_analysis import fetch_cart


def _gaps_payload(gaps: list[Gap]) -> list[dict[str, Any]]:
    return [
        {
            "nutrient": g.nutrient, "label": g.label, "target": round(g.target),
            "actual": round(g.actual), "diff": round(g.diff), "severity": g.severity,
            "human": g.human, "food": gap_to_food(g),
        }
        for g in gaps
    ]


async def _overview_now(user_id: str) -> dict[str, Any]:
    """Що гість реально купує на день проти того, що йому треба."""
    goal_row = await repo.get_goal(user_id)
    targets = goals.targets_from_row(goal_row)

    async with silpo(user_id) as api:
        ctx, _products, meta = await fetch_cart(api)
        if ctx is None:
            return {"configured": bool(goal_row), "targets": targets.as_dict(),
                    "reason": meta.get("reason"), "gaps": [], "per_day": {}}
        orders = await habits.fetch_offline_orders(api, ctx)
        details = await habits.load_details_for(
            api, ctx, [l["slug"] for o in orders for l in o.items if l.get("slug")]
        )

    household = int((goal_row or {}).get("household_size") or 1)
    days = max((orders[0].created_at - orders[-1].created_at).days, 7) if len(orders) > 1 else 7

    totals = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    counted = 0
    for order in orders:
        for line in order.items:
            product = details.get(line.get("slug"))
            if product is None or not product.has_nutrition:
                continue
            grams = (planner._grams_of(product)) * (line.get("quantity") or 1)
            for key, value in planner._contribution(product, grams).items():
                totals[key] += value
            counted += 1

    per_day = {k: round(v / days / household, 1) for k, v in totals.items()}
    gaps = compare(targets, per_day)

    return {
        "configured": bool(goal_row and goal_row.get("goal")),
        "targets": targets.as_dict(),
        "per_day": per_day,
        "period_days": days,
        "products_counted": counted,
        "gaps": _gaps_payload(gaps),
        "household": household,
        "budget": (goal_row or {}).get("weekly_budget"),
    }


async def overview(user_id: str, refresh: bool = False) -> dict[str, Any]:
    """Кешований огляд. Довгий перерахунок іде у фон — інакше тунель дає 502."""
    if refresh:
        jobs.invalidate("overview", user_id)
    return await jobs.cached_or_start("overview", user_id, lambda: _overview_now(user_id))


async def _build_plan_now(
    user_id: str,
    budget: float | None = None,
    preferences: str | None = None,
    household: int | None = None,
    prefer_promo: bool = True,
) -> dict[str, Any]:
    """Головна дія: зібрати кошик на тиждень під ціль, бюджет і побажання."""
    goal_row = await repo.get_goal(user_id)
    targets = goals.targets_from_row(goal_row)
    household = household or int((goal_row or {}).get("household_size") or 1)
    if budget is None and goal_row and goal_row.get("weekly_budget"):
        budget = float(goal_row["weekly_budget"])

    async with silpo(user_id) as api:
        ctx, _products, meta = await fetch_cart(api)
        if ctx is None:
            return {"error": meta.get("reason", "Кошик Сільпо недоступний"), "items": []}

        orders = await habits.fetch_offline_orders(api, ctx)
        try:
            restrictions_payload = await api.call(T.GET_FOOD_RESTRICTIONS, {})
        except Exception:  # noqa: BLE001
            restrictions_payload = None
        restrictions = (
            [] if T.restrictions_are_empty(restrictions_payload)
            else al.parse_restrictions(restrictions_payload)
        )

        plan = await planner.build_weekly_plan(
            api, ctx, targets, orders, restrictions, budget=budget, household=household,
            preferences=preferences, prefer_promo=prefer_promo,
        )

    payload = plan.as_dict()
    payload["targets"] = targets.as_dict()
    payload["restrictions"] = [r.label for r in restrictions]
    payload["preferences"] = preferences

    from app.llm import advisor
    explanation = await advisor.explain_plan(payload, targets.as_dict())
    if explanation:
        payload["summary_text"] = explanation
    saved = await repo.save_plan(user_id, payload)
    payload["plan_id"] = str(saved.get("id"))
    return payload


async def build_plan(
    user_id: str,
    budget: float | None = None,
    preferences: str | None = None,
    household: int | None = None,
    prefer_promo: bool = True,
) -> dict[str, Any]:
    """Ставить збірку кошика у фон і одразу повертає керування."""
    jobs.invalidate("plan", user_id)
    return await jobs.start(
        "plan", user_id,
        lambda: _build_plan_now(user_id, budget, preferences, household, prefer_promo),
    )


async def plan_status(user_id: str) -> dict[str, Any]:
    cached = jobs.get_cached("plan", user_id)
    if cached is not None:
        return {**cached, "building": jobs.is_running("plan", user_id)}
    return {
        "building": jobs.is_running("plan", user_id),
        "error": jobs.last_error("plan", user_id),
        "items": [],
    }


async def apply_plan(user_id: str, plan_id: str) -> dict[str, Any]:
    """Записує зібраний кошик у Сільпо — реальний write-виклик MCP."""
    plan = await repo.get_plan(user_id, plan_id)
    if not plan:
        raise KeyError("План не знайдено")

    items = plan.get("items_json") or []
    products = [
        {
            "productId": item["product_id"],
            "quantity": item.get("quantity", 1),
        }
        for item in items if item.get("product_id")
    ]
    if not products:
        raise RuntimeError("У плані немає товарів із коректним id")

    async with silpo(user_id) as api:
        ctx, _cart_products, _meta = await fetch_cart(api)
        if ctx is None:
            raise RuntimeError("Кошик Сільпо недоступний")
        result = await api.call(T.ADD_OR_UPDATE_CART, {
            "shoppingCartId": ctx.cart_id,
            "products": [
                {**p, "companyId": ctx.company_id, "branchId": ctx.branch_id} for p in products
            ],
        })

    await repo.mark_plan_applied(plan_id)
    return {"applied": True, "added": len(products), "cart_id": ctx.cart_id, "result": result}
