"""Іменовані tools Сільпо + витягування полів за ФАКТИЧНОЮ схемою.

Схеми звірені пробними викликами (scripts/probe_mcp.py). Найважливіше:
товар у Сільпо не існує сам по собі — деталі доступні лише в контексті
магазину й таймслоту, тому майже всі виклики потребують CartContext.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GET_MY_CART = "silpo_get_my_shopping_cart"
GET_CART_BY_ID = "silpo_get_shopping_cart_by_id"
GET_TIME_SLOTS = "silpo_get_time_slots"
GET_PRODUCT_DETAILS = "silpo_get_product_details"
GET_SIMILAR_PRODUCTS = "silpo_get_similar_products"
GET_FOOD_RESTRICTIONS = "silpo_get_my_food_restrictions"
ADD_OR_UPDATE_CART = "silpo_add_or_update_cart_products"
REMOVE_CART_PRODUCTS = "silpo_remove_cart_products"
GET_ONLINE_ORDERS = "silpo_get_my_online_orders"
GET_OFFLINE_ORDERS = "silpo_get_my_offline_orders"
GET_MY_FAMILY = "silpo_get_my_family"
GET_MY_PROFILE = "silpo_get_my_profile"
GET_LOYALTY = "silpo_get_loyalty_info"
ADD_OR_UPDATE_FAVORITES = "silpo_add_or_update_favorite_products"
FIND_PRODUCTS_BATCH = "silpo_find_products_batch"
GET_PROMOTIONS = "silpo_get_promotions"
GET_PRODUCTS = "silpo_get_products"


@dataclass
class CartContext:
    """Контекст, без якого product-tools повертають 400.

    branchId/deliveryType/timeslot беруться з silpo_get_shopping_cart_by_id.
    """

    cart_id: str
    branch_id: str
    company_id: str | None
    delivery_type: str
    timeslot_start: str
    timeslot_end: str

    def product_args(self, slug: str, **extra: Any) -> dict[str, Any]:
        return {
            "branchId": self.branch_id,
            "slug": slug,
            "deliveryType": self.delivery_type,
            "timeslotStart": self.timeslot_start,
            "timeslotEnd": self.timeslot_end,
            **extra,
        }

    def as_args(self, **extra: Any) -> dict[str, Any]:
        return {
            "branchId": self.branch_id,
            "deliveryType": self.delivery_type,
            "timeslotStart": self.timeslot_start,
            "timeslotEnd": self.timeslot_end,
            **extra,
        }


def is_mcp_error(payload: Any) -> str | None:
    """MCP іноді віддає помилку валідації текстом у content, а не isError."""
    if isinstance(payload, str) and payload.startswith("MCP error"):
        return payload
    if isinstance(payload, dict) and payload.get("success") is False:
        return str(payload)[:300]
    return None


def cart_context(cart_payload: Any, cart_id: str) -> CartContext | None:
    """Розбирає відповідь silpo_get_shopping_cart_by_id.

    Формат: {"success": true, "cart": {"id", "deliveryType",
             "timeslot": {"start","end"},
             "shipments": [{"companyId","branchId","products":[...]}]}}
    """
    cart = cart_payload.get("cart") if isinstance(cart_payload, dict) else None
    if not isinstance(cart, dict):
        return None
    shipments = cart.get("shipments") or []
    if not shipments:
        return None
    first = shipments[0]
    timeslot = cart.get("timeslot") or {}
    if not (first.get("branchId") and timeslot.get("start")):
        return None
    return CartContext(
        cart_id=str(cart.get("id") or cart_id),
        branch_id=str(first["branchId"]),
        company_id=first.get("companyId"),
        delivery_type=str(cart.get("deliveryType") or "SelfPickup"),
        timeslot_start=str(timeslot["start"]),
        timeslot_end=str(timeslot.get("end") or timeslot["start"]),
    )


def cart_products(cart_payload: Any) -> list[dict[str, Any]]:
    """Позиції кошика з усіх shipments."""
    cart = cart_payload.get("cart") if isinstance(cart_payload, dict) else None
    if not isinstance(cart, dict):
        return []
    out: list[dict[str, Any]] = []
    for shipment in cart.get("shipments") or []:
        for product in shipment.get("products") or []:
            out.append({**product, "_shipmentId": shipment.get("id")})
    return out


def offline_order_items(order: dict[str, Any]) -> list[dict[str, Any]]:
    """Позиції офлайн-чека. Кожна має catalogProduct зі slug (може бути None)."""
    items: list[dict[str, Any]] = []
    for line in order.get("products") or []:
        catalog = line.get("catalogProduct") or {}
        items.append(
            {
                "name": line.get("name"),
                "slug": catalog.get("slug"),
                "product_id": catalog.get("id"),
                "unit": line.get("unit"),
                "quantity": line.get("quantity") or 1,
                "price": line.get("price"),
                "image": line.get("image") or catalog.get("image"),
            }
        )
    return items


def restrictions_are_empty(payload: Any) -> bool:
    """`all-food` у профілі Сільпо означає «обмежень немає»."""
    if not isinstance(payload, dict):
        return True
    items = payload.get("restrictions") or []
    if not items:
        return True
    slugs = {str(r.get("slug") or "").lower() for r in items if isinstance(r, dict)}
    return not (slugs - {"all-food", "", "none"})
