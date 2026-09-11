"""«Живі дані» — що саме застосунок зробив через MCP «Сільпо».

Не сирий лог для інженера, а зрозумілий перелік дій із доказом: скільки
викликів, коли, і чи був серед них запис. Сирий JSON-RPC лишається поруч —
для технічного режиму на демо.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.mcp import logbus
from app.security.session import current_user_id

router = APIRouter(tags=["live"])

# Людські назви дій. Порядок = порядок у сценарії роботи застосунку.
ACTIONS: tuple[tuple[str, str], ...] = (
    ("silpo_get_my_shopping_cart", "Підключились до акаунта"),
    ("silpo_get_shopping_cart_by_id", "Прочитали контекст кошика"),
    ("silpo_get_time_slots", "Оновили слот доставки"),
    ("silpo_get_my_profile", "Прочитали профіль"),
    ("silpo_get_my_food_restrictions", "Перевірили обмеження й алергії"),
    ("silpo_get_my_offline_orders", "Завантажили історію чеків"),
    ("silpo_get_product_details", "Звірили склад і ціни товарів"),
    ("silpo_find_products_batch", "Шукали реалістичні альтернативи"),
    ("silpo_get_my_coupons", "Перевірили ваші купони"),
    ("silpo_add_or_update_cart_products", "Записали кошик у Сільпо"),
)

WRITE_TOOLS = {"silpo_add_or_update_cart_products", "silpo_remove_cart_products",
               "silpo_add_or_update_favorite_products"}


@router.get("/live/activity")
async def activity(limit: int = 300, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    entries = logbus.tail(user_id, limit)

    counts: dict[str, int] = {}
    last_at: dict[str, str] = {}
    for entry in entries:
        tool = entry.get("tool") or entry.get("name") or ""
        if not tool:
            continue
        counts[tool] = counts.get(tool, 0) + 1
        when = entry.get("at") or entry.get("timestamp")
        if when:
            last_at[tool] = when

    steps = [
        {
            "tool": tool,
            "label": label,
            "calls": counts.get(tool, 0),
            "done": counts.get(tool, 0) > 0,
            "at": last_at.get(tool),
            "is_write": tool in WRITE_TOOLS,
        }
        for tool, label in ACTIONS
    ]

    return {
        "endpoint": get_settings().silpo_mcp_url,
        "demo_mode": get_settings().demo_mode,
        "steps": steps,
        "total_calls": sum(counts.values()),
        "writes": sum(counts.get(t, 0) for t in WRITE_TOOLS),
        "tools_used": len([t for t, n in counts.items() if n]),
    }
