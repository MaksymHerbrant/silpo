"""Розвідка реальної схеми MCP Сільпо — ЗАПУСТИ ЦЕ ПЕРЕД ДЕМО.

Ми навмисно не вигадували структуру відповідей silpo_*; парсер у
app/nutrition/parser.py толерантний до різних форматів. Цей скрипт друкує
фактичний JSON, щоб за потреби додати знайдені ключі в KEY_SYNONYMS.

Використання (потрібен уже під'єднаний акаунт Сільпо в БД):
    cd backend
    .venv/bin/python scripts/probe_mcp.py --user <uuid> --tools
    .venv/bin/python scripts/probe_mcp.py --user <uuid> --cart
    .venv/bin/python scripts/probe_mcp.py --user <uuid> --product 12345

Якщо токена ще немає: підніми бекенд, зайди в Mini App, натисни
«Під'єднати Сільпо», і візьми user id з таблиці users.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def dump(label: str, data) -> None:
    print(f"\n===== {label} =====")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:8000])


def schema_of(node, prefix="", out=None, depth=0):
    """Плаский зріз ключів -> тип/приклад, щоб швидко побачити структуру."""
    out = {} if out is None else out
    if depth > 6:
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                schema_of(v, path, out, depth + 1)
            else:
                out[path] = f"{type(v).__name__} = {str(v)[:60]}"
    elif isinstance(node, list) and node:
        schema_of(node[0], f"{prefix}[]", out, depth + 1)
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True, help="users.id (uuid) з Supabase")
    ap.add_argument("--tools", action="store_true", help="показати tools/list")
    ap.add_argument("--cart", action="store_true", help="кошик + деталі першого товару")
    ap.add_argument("--product", help="показати silpo_get_product_details для id")
    ap.add_argument("--orders", action="store_true")
    ap.add_argument("--restrictions", action="store_true")
    args = ap.parse_args()

    from app.mcp import tools as T
    from app.mcp.gateway import silpo

    async with silpo(args.user) as api:
        if args.tools or not any([args.cart, args.product, args.orders, args.restrictions]):
            tools = await api.list_tools()
            print(f"Доступно tools: {len(tools)}")
            for t in tools:
                print(f"  - {t['name']}: {(t.get('description') or '')[:90]}")

        if args.cart:
            head = await api.call(T.GET_MY_CART, {})
            dump("silpo_get_my_shopping_cart", head)
            cart_id = T.pick(head, "cartId", "id")
            cart = await api.call(T.GET_CART_BY_ID, {"cartId": cart_id, "id": cart_id})
            dump("silpo_get_shopping_cart_by_id", cart)
            items = T.find_list_of_items(cart)
            print(f"\nЗнайдено позицій: {len(items)}")
            if items:
                pid = T.item_product_id(items[0])
                detail = await api.call(T.GET_PRODUCT_DETAILS, {"productId": pid})
                dump(f"silpo_get_product_details({pid})", detail)
                dump("СХЕМА product_details", schema_of(detail))

        if args.product:
            detail = await api.call(T.GET_PRODUCT_DETAILS, {"productId": args.product})
            dump("silpo_get_product_details", detail)
            dump("СХЕМА", schema_of(detail))
            from app.nutrition.parser import parse_product

            info = parse_product(detail, args.product)
            print("\nРозпізнано парсером:")
            print("  title:", info.title, "| brand:", info.brand, "| own_brand:", info.is_own_brand)
            print("  nutrition:", info.nutrition)
            print("  джерела полів:", info.nutrition.sources)
            print("  ВІДСУТНІ поля:", info.nutrition.missing)

        if args.orders:
            orders = await api.call(T.GET_ONLINE_ORDERS, {"limit": 5})
            dump("silpo_get_my_online_orders", orders)
            dump("СХЕМА", schema_of(orders))

        if args.restrictions:
            r = await api.call(T.GET_FOOD_RESTRICTIONS, {})
            dump("silpo_get_my_food_restrictions", r)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
