"""Чи зʼявився новий чек.

Дешева перевірка замість дорогої перебудови: одна сторінка офлайн-замовлень
(10 найновіших) проти збереженого відбитка. Повна побудова — це 30+ викликів
MCP; перевірка — три-чотири.

Відбиток беремо з НАЙНОВІШОГО чека: дата плюс сума. Нова покупка змінює обидва.
"""
from __future__ import annotations

from typing import Any

from app.mcp import tools as T
from app.services import habits

EMPTY = "empty"


def signature_from(orders: list[Any]) -> str:
    """Відбиток за вже прочитаними чеками — без жодного зайвого виклику."""
    if not orders:
        return EMPTY
    page = orders[: habits.PAGE_SIZE]
    newest = max(page, key=lambda o: o.created_at)
    return f"{len(page)}:{newest.created_at.isoformat()}:{round(newest.total, 2)}"


async def probe(api, ctx: T.CartContext) -> str | None:
    """Один виклик MCP: чи змінилася верхівка списку чеків."""
    payload = await api.call(
        T.GET_OFFLINE_ORDERS, ctx.as_args(limit=habits.PAGE_SIZE, offset=0)
    )
    if T.is_mcp_error(payload):
        return None
    return signature_from(habits.parse_orders(payload))
