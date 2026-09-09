"""Фікстури для DEMO_MODE=true — розробка фронтенду без живого MCP.

Це НЕ підміна реального сценарію демо для журі: у продовому режимі
(DEMO_MODE=false) усі дані йдуть виключно з https://mcp.silpo.ua/mcp.
Структура тут навмисно "неохайна" (різні формати полів), щоб перевіряти
толерантність парсера.
"""
from __future__ import annotations

from typing import Any

CART_ID = "demo-cart-1"

_PRODUCTS: dict[str, dict[str, Any]] = {
    "101": {
        "id": 101, "title": "Йогурт питний полуничний 2.5%", "brand": "Молокія",
        "weight": 290, "unit": "г",
        "ingredients": "Молоко нормалізоване, цукор, пюре полуниці, крохмаль, закваска",
        "nutritionFacts": [
            {"name": "Енергетична цінність", "value": "84 ккал"},
            {"name": "Білки", "value": "2.8 г"},
            {"name": "Жири", "value": "2.5 г"},
            {"name": "у т.ч. насичені жири", "value": "1.6 г"},
            {"name": "Вуглеводи", "value": "12.9 г"},
            {"name": "у т.ч. цукри", "value": "12.1 г"},
            {"name": "Сіль", "value": "0.1 г"},
        ],
    },
    "102": {
        "id": 102, "title": "Йогурт натуральний 2.5% без цукру", "brand": "Премія",
        "weight": 300, "ingredients": "Молоко нормалізоване, закваска",
        "nutritionFacts": [
            {"name": "Енергетична цінність", "value": "58 ккал"},
            {"name": "Білки", "value": "4.2 г"},
            {"name": "Жири", "value": "2.5 г"},
            {"name": "насичені жири", "value": "1.5 г"},
            {"name": "Вуглеводи", "value": "4.1 г"},
            {"name": "цукри", "value": "4.1 г"},
            {"name": "Сіль", "value": "0.1 г"},
        ],
    },
    "201": {
        "id": 201, "title": "Пластівці кукурудзяні в глазурі", "brand": "Start!",
        "weight": 500, "ingredients": "Кукурудзяна крупа, цукор, глюкозний сироп, сіль, солод",
        "nutrition": {"calories": 384, "protein": 5.5, "fat": 2.4, "saturatedFat": 0.9,
                      "carbohydrates": 85.1, "sugar": 36.4, "fiber": 2.1, "salt": 0.6},
    },
    "202": {
        "id": 202, "title": "Пластівці вівсяні без цукру", "brand": "Премія",
        "weight": 800, "ingredients": "Зерно вівса цільне",
        "nutrition": {"calories": 352, "protein": 12.3, "fat": 6.2, "saturatedFat": 1.1,
                      "carbohydrates": 59.5, "sugar": 1.1, "fiber": 10.0, "salt": 0.02},
    },
    "301": {
        "id": 301, "title": "Куряче філе охолоджене", "brand": "Наша Ряба",
        "weight": 700, "ingredients": "Філе куряче",
        "nutrition": {"calories": 110, "protein": 23.0, "fat": 1.8, "saturatedFat": 0.5,
                      "carbohydrates": 0.0, "sugar": 0.0, "salt": 0.1},
    },
    "302": {
        "id": 302, "title": "Броколі заморожені", "brand": "Зелена Країна",
        "weight": 400, "ingredients": "Капуста броколі",
        "nutrition": {"calories": 34, "protein": 2.8, "fat": 0.4, "saturatedFat": 0.1,
                      "carbohydrates": 4.0, "sugar": 1.7, "fiber": 2.6, "salt": 0.03},
    },
    "401": {
        "id": 401, "title": "Чипси картопляні зі смаком паприки", "brand": "Люкс",
        "weight": 133, "ingredients": "Картопля, олія соняшникова, сіль, паприка, глюкоза",
        "nutrition": {"calories": 526, "protein": 6.1, "fat": 32.0, "saturatedFat": 3.4,
                      "carbohydrates": 51.0, "sugar": 2.1, "fiber": 4.0, "salt": 1.4},
    },
    "402": {
        "id": 402, "title": "Хлібці цільнозернові", "brand": "Премія",
        "weight": 100, "ingredients": "Борошно цільнозернове пшеничне, вода, сіль",
        "nutrition": {"calories": 320, "protein": 11.0, "fat": 2.0, "saturatedFat": 0.4,
                      "carbohydrates": 60.0, "sugar": 1.0, "fiber": 12.0, "salt": 0.5},
    },
    "501": {
        # Навмисно без харчової цінності — перевірка fallback-логіки
        "id": 501, "title": "Пакет-майка Сільпо", "brand": "Сільпо", "weight": 0,
    },
}

_SIMILAR = {"101": ["102"], "201": ["202"], "401": ["402"]}


async def call(name: str, args: dict[str, Any]) -> Any:
    from app.mcp import tools as T

    if name == T.GET_MY_CART:
        return {"cartId": CART_ID, "guestId": "demo-guest"}
    if name == T.GET_CART_BY_ID:
        return {
            "id": CART_ID, "branchId": 2043, "deliveryType": "delivery",
            "timeslotId": "ts-1",
            "items": [
                {"productId": 101, "quantity": 2, "title": _PRODUCTS["101"]["title"]},
                {"productId": 201, "quantity": 1, "title": _PRODUCTS["201"]["title"]},
                {"productId": 301, "quantity": 1, "title": _PRODUCTS["301"]["title"]},
                {"productId": 302, "quantity": 2, "title": _PRODUCTS["302"]["title"]},
                {"productId": 401, "quantity": 3, "title": _PRODUCTS["401"]["title"]},
                {"productId": 501, "quantity": 1, "title": _PRODUCTS["501"]["title"]},
            ],
        }
    if name == T.GET_TIME_SLOTS:
        return {"timeSlots": [{"id": "ts-1", "date": "2026-09-10", "from": "10:00", "to": "12:00"}]}
    if name == T.GET_PRODUCT_DETAILS:
        pid = str(args.get("productId") or args.get("id") or "")
        return _PRODUCTS.get(pid, {"id": pid, "title": f"Товар {pid}"})
    if name == T.GET_FOOD_RESTRICTIONS:
        return {"restrictions": [{"name": "Без лактози"}, {"name": "Алергія на арахіс"}]}
    if name == T.GET_SIMILAR_PRODUCTS:
        pid = str(args.get("productId") or args.get("id") or "")
        return {"products": [_PRODUCTS[p] for p in _SIMILAR.get(pid, []) if p in _PRODUCTS]}
    if name == T.ADD_OR_UPDATE_CART:
        return {"success": True, "cartId": CART_ID, "applied": args}
    if name == T.GET_ONLINE_ORDERS:
        weeks = [
            ("2026-08-11", [("101", 2), ("201", 1), ("401", 4)]),
            ("2026-08-18", [("101", 1), ("202", 1), ("401", 2), ("302", 1)]),
            ("2026-08-25", [("102", 2), ("202", 1), ("301", 2), ("302", 2)]),
            ("2026-09-01", [("102", 2), ("202", 2), ("301", 1), ("302", 3), ("401", 1)]),
        ]
        return {
            "orders": [
                {
                    "id": f"order-{i}", "createdAt": f"{date}T12:00:00Z", "status": "delivered",
                    "items": [
                        {"productId": int(pid), "quantity": q, "title": _PRODUCTS[pid]["title"]}
                        for pid, q in items
                    ],
                }
                for i, (date, items) in enumerate(weeks, start=1)
            ]
        }
    if name == T.GET_MY_FAMILY:
        return {"members": [{"role": "child", "birthYear": 2018}]}
    return {"warning": f"DEMO_MODE: tool {name} не змодельовано", "args": args}


async def list_tools() -> list[dict[str, Any]]:
    from app.mcp import tools as T

    names = [
        T.GET_MY_CART, T.GET_CART_BY_ID, T.GET_TIME_SLOTS, T.GET_PRODUCT_DETAILS,
        T.GET_FOOD_RESTRICTIONS, T.GET_SIMILAR_PRODUCTS, T.ADD_OR_UPDATE_CART,
        T.GET_ONLINE_ORDERS, T.GET_MY_FAMILY,
    ]
    return [{"name": n, "description": "DEMO_MODE fixture", "input_schema": {}} for n in names]
