"""Кошик застосунку: збірна точка з усіх екранів.

Головне архітектурне рішення: товар з будь-якого екрана лягає в наш кошик, а
НЕ одразу в кошик Сільпо. Запис у MCP один — на «Оформити». Так гість збирає
набір по кількох екранах, змінює кількість і передумує без наслідків, а ми
не смітимо в його реальному кошику.

Після запису кошик Сільпо перечитується — це і є доказ, що write справді
відбувся, а не «ми відправили і сподіваємось».
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import repo
from app.mcp import tools as T
from app.mcp.gateway import silpo
from app.security.session import current_user_id
from app.services.cart_analysis import fetch_cart

router = APIRouter(tags=["basket"])


class CartItemIn(BaseModel):
    product_id: str
    slug: str | None = None
    name: str | None = None
    image: str | None = None
    price: float | None = None
    quantity: int = 1
    source: str | None = None       # nutrition | promo | analytics | plan
    # Якщо товар додано з пропозиції агента — закриваємо її як прийняту
    decision_id: str | None = None


class QuantityIn(BaseModel):
    quantity: int


def _view(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = [
        {
            "id": r.get("id"),
            "product_id": r.get("product_id"),
            "slug": r.get("slug"),
            "name": r.get("name"),
            "image": r.get("image"),
            "price": float(r.get("price") or 0),
            "quantity": int(r.get("quantity") or 1),
            "source": r.get("source"),
            "line_total": round(float(r.get("price") or 0) * int(r.get("quantity") or 1), 2),
        }
        for r in rows
    ]
    return {
        "items": items,
        "count": sum(i["quantity"] for i in items),
        "positions": len(items),
        "total": round(sum(i["line_total"] for i in items), 2),
    }


@router.get("/cart")
async def get_cart(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    return _view(await repo.cart_items(user_id))


@router.post("/cart/items")
async def add_item(payload: CartItemIn, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    await repo.cart_add(user_id, payload.model_dump())
    if payload.decision_id:
        row = await repo.get_decision(user_id, payload.decision_id)
        if row and row.get("accepted") is None:
            await repo.decide(payload.decision_id, True)
    return _view(await repo.cart_items(user_id))


@router.patch("/cart/items/{item_id}")
async def set_quantity(
    item_id: str, payload: QuantityIn, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    await repo.cart_set_quantity(user_id, item_id, payload.quantity)
    return _view(await repo.cart_items(user_id))


@router.delete("/cart/items/{item_id}")
async def remove_item(item_id: str, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    await repo.cart_remove(user_id, item_id)
    return _view(await repo.cart_items(user_id))


@router.post("/cart/checkout")
async def checkout(user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Єдиний write у MCP за весь флоу. Після нього — перечитування як доказ."""
    rows = await repo.cart_items(user_id)
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Кошик порожній")

    async with silpo(user_id) as api:
        ctx, _cart, _meta = await fetch_cart(api)
        if ctx is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Кошик Сільпо недоступний")
        result = await api.call(T.ADD_OR_UPDATE_CART, {
            "shoppingCartId": ctx.cart_id,
            "products": [
                {
                    "productId": r["product_id"],
                    "quantity": max(int(r.get("quantity") or 1), 1),
                    "companyId": ctx.company_id,
                    "branchId": ctx.branch_id,
                }
                for r in rows if r.get("product_id")
            ],
        })
        _c, after, _m = await fetch_cart(api)

    await repo.cart_clear(user_id)
    return {
        "applied": True,
        "added": len(rows),
        "cart_total": round(sum(float(p.get("total") or 0) for p in after), 2),
        "cart_now": [{"name": p.get("name"), "quantity": p.get("quantity")} for p in after],
        "checkout_hint": "Відкрийте кошик у застосунку Сільпо, щоб підтвердити замовлення",
        "mcp_result": result,
    }
