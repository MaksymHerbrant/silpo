"""Екран «Харчування» і пасивний чіп корисності кошика.

Обидва відповіді детерміновані: жодне число тут не проходить через модель.
Чіп кошика рахується з назв товарів, без викликів MCP, тому віддається миттєво.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.db import repo
from app.mcp import tools as T
from app.nutrition import allergens as al
from app.nutrition import categories as cats
from app.nutrition.parser import parse_product
from app.mcp.gateway import silpo
from app.security.session import current_user_id
from app.agent import analyst
from app.services import cache, habits, jobs, nutrition_view, pipeline
from app.services.cart_analysis import fetch_cart

router = APIRouter(tags=["nutrition"])


@router.get("/nutrition/summary")
async def summary(
    period: str = Query("week", pattern="^(week|month|all)$"),
    refresh: bool = False,
    user_id: str = Depends(current_user_id),
) -> dict[str, Any]:
    """Бал 1–10, одне речення і деталі за розгорткою.

    Чеки кешуються окремо для кожного періоду. БЖВ беремо з уже побудованого
    плану — там деталі товарів уже прочитані, тож зайвих викликів MCP немає.
    """
    job = f"nutrition:{period}"
    if refresh:
        jobs.invalidate(job, user_id)
        jobs.reset_failures(job, user_id)
    else:
        row = await cache.load(user_id, job)
        if row and row.get("payload"):
            return {**row["payload"], "cached": True, "built_at": row.get("built_at")}

    goal_row = await repo.get_goal(user_id) or {}
    plan_cache = await pipeline.cached_plan_async(user_id)

    async def _factory() -> dict[str, Any]:
        async with silpo(user_id) as api:
            ctx, _cart, meta = await fetch_cart(api)
            if ctx is None:
                return {"has_data": False, "reason": meta.get("reason", "Дані Сільпо недоступні")}
            orders = await habits.fetch_offline_orders(api, ctx)
            result = nutrition_view.build(orders, plan_cache, goal_row.get("goal"), period)
            await _fill_products(api, ctx, result, _restrictions_from(plan_cache),
                                 (plan_cache or {}).get('items'))
        await cache.store(user_id, job, None, result)
        return result

    return await jobs.cached_or_start(job, user_id, _factory)


MAX_PICKS_PER_CATEGORY = 3


def _restrictions_from(plan: dict[str, Any] | None) -> list[al.Restriction]:
    """Обмеження гостя з уже побудованого плану — без зайвих викликів MCP."""
    rows = ((plan or {}).get("profile") or {}).get("restrictions") or []
    return [
        al.Restriction(slug=r["slug"], label=r["label"], triggers=tuple(r.get("triggers") or ()))
        for r in rows if r.get("slug")
    ]


async def _fill_products(
    api, ctx, result: dict[str, Any], restrictions: list[al.Restriction] | None = None,
    plan_items: list[dict[str, Any]] | None = None,
) -> None:
    """Підставляє живі товари під рекомендації — одним викликом на всі категорії.

    Беремо найдешевші доступні позиції: рекомендація «додай овочів» без
    конкретних товарів і цін нічого не варта, а дорогі позиції гість
    просто не візьме.
    """
    recs = result.get("recommendations") or []
    if not recs:
        return
    queries: list[str] = []
    for rec in recs:
        queries.extend(rec.get("queries") or [])
    if not queries:
        return
    try:
        payload = await api.call(T.FIND_PRODUCTS_BATCH, ctx.as_args(products=queries[:12]))
    except Exception:  # noqa: BLE001 — без товарів рекомендація все одно корисна
        return
    if T.is_mcp_error(payload) or not isinstance(payload, dict):
        return

    by_query: dict[str, list[dict[str, Any]]] = {}
    for block in payload.get("queries") or []:
        by_query[str(block.get("query"))] = [
            {
                "product_id": str(raw.get("id") or ""),
                "slug": raw.get("slug"),
                "name": raw.get("name"),
                "image": raw.get("image"),
                "price": raw.get("price"),
                "old_price": raw.get("oldPrice"),
                "on_promotion": bool(raw.get("oldPrice") and raw.get("price")
                                     and raw["oldPrice"] > raw["price"]),
            }
            for raw in (block.get("products") or [])
            if raw.get("available") is not False and raw.get("price")
        ]

    has_restrictions = any(r.kind == al.KIND_ALLERGEN for r in (restrictions or []))
    habit_names = [
        (i.get("name") or "")[:40] for i in (plan_items or [])
        if (i.get("habit") or {}).get("kind") == "stable"
    ]
    for rec in recs:
        picks: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in rec.get("queries") or []:
            for item in by_query.get(query, []):
                if item["slug"] in seen:
                    continue
                # Пошук Сільпо нечіткий: «Каша» віддає каву, «Індичка» —
                # корм для котів. Тому довіряємо не запиту, а категорії
                # знайденого товару: не збіглась — не пропонуємо.
                if cats.categorize(item.get("name") or "") != rec["key"]:
                    continue
                if not cats.recommendable(item.get("name") or ""):
                    continue
                seen.add(item["slug"])
                picks.append(item)
        # Акційні першими, далі найдешевші — і те, і те допомагає взяти
        # Акційні першими, далі найдешевші — і те, і те допомагає взяти
        picks.sort(key=lambda i: (not i["on_promotion"], i["price"]))

        # Останнє слово за моделлю: вона розуміє, що банановий йогурт не
        # є фруктом, і зважає на те, що гість уже купує.
        chosen = await analyst.pick_products(rec["label"], picks, habit_names)
        if chosen.get("picks"):
            order = {slug: n for n, slug in enumerate(chosen["picks"])}
            picks = sorted(
                (p for p in picks if p["slug"] in order), key=lambda p: order[p["slug"]]
            )
        if chosen.get("advice"):
            rec["advice"] = chosen["advice"]

        rec["products"] = await _safe_picks(api, ctx, picks, restrictions or [])
        if has_restrictions and not rec["products"]:
            rec["note"] = (
                "Конкретних товарів не радимо: у каталозі немає складу, "
                "а з вашими обмеженнями вгадувати не можна."
            )


async def _safe_picks(api, ctx, picks, restrictions) -> list[dict[str, Any]]:
    """Звіряє кандидатів зі складом. Порада — це теж обіцянка безпеки.

    Без цього людині з непереносимістю глютену пропонувались макарони: назва
    маркерів не містить, а склад ніхто не читав. Тому читаємо картку кожного
    кандидата й відкидаємо ті, що конфліктують із профілем. Товар без складу
    у каталозі не викидаємо, але позначаємо — незнання не є гарантією.
    """
    blocking_kinds = [r for r in restrictions if r.kind == al.KIND_ALLERGEN]
    out: list[dict[str, Any]] = []
    for item in picks:
        if len(out) >= MAX_PICKS_PER_CATEGORY:
            break
        if not blocking_kinds:
            # Вподобання (наприклад «менше цукру») не є питанням безпеки —
            # тут невідомий склад не привід мовчати.
            out.append({**item, "composition_known": None})
            continue
        try:
            detail = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(item["slug"]))
        except Exception:  # noqa: BLE001
            continue
        if T.is_mcp_error(detail):
            continue
        product = parse_product(detail, fallback_slug=item["slug"],
                                fallback_title=item.get("name") or "")
        if al.blocking(al.check_product(product, blocking_kinds)):
            continue
        known = bool(product.allergens_text or product.ingredients)
        if not known:
            # У гостя є алерген, а складу товару каталог не дає. Це ПОРАДА,
            # а не вимушена заміна: мовчання тут краще за ризик. Перевірено —
            # інакше людині з непереносимістю глютену радились макарони,
            # у яких склад просто не заповнено.
            continue
        out.append({**item, "composition_known": True})
    return out


@router.get("/coupons")
async def coupons(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Купони гостя. Їх видає Сільпо персонально — це реальна вигода, а не наша."""
    row = await cache.load(user_id, "coupons")
    if row and row.get("payload"):
        return {**row["payload"], "cached": True}

    async with silpo(user_id) as api:
        try:
            payload = await api.call(T.GET_MY_COUPONS, {})
        except Exception:  # noqa: BLE001
            return {"coupons": [], "reason": "Купони зараз недоступні"}
    if T.is_mcp_error(payload) or not isinstance(payload, dict):
        return {"coupons": [], "reason": "Купони зараз недоступні"}

    items = [
        {
            "id": c.get("id"),
            "description": c.get("description"),
            "reward": (f"{c.get('rewardSign') or ''}{c.get('rewardValue')} "
                       f"{c.get('rewardUnit') or ''}").strip(),
            "until": c.get("endDate"),
            "image": c.get("image"),
            "limits": c.get("limitText"),
        }
        for c in (payload.get("coupons") or [])
        if c.get("active")
    ]
    result = {"coupons": items, "count": len(items)}
    await cache.store(user_id, "coupons", None, result)
    return result


@router.get("/cart/rating")
async def rating(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Пасивний чіп біля «Оформити». None, якщо в кошику немає їжі."""
    items = await repo.cart_items(user_id)
    normalized = [
        {
            "name": r.get("name"),
            "price": float(r.get("price") or 0),
            "quantity": int(r.get("quantity") or 1),
        }
        for r in items
    ]
    return {"rating": nutrition_view.cart_rating(normalized)}
