"""Інструменти, які агент викликає САМ.

Ключове рішення архітектури: моделі дається не 40 сирих tools MCP, а десяток
осмислених дій. Модель вирішує, ЩО і в якому порядку робити; кожен інструмент
усередині ходить у MCP і повертає стислий результат.

Розподіл відповідальності жорсткий:
  * модель — оркестрація: зрозуміти ціль, дібрати кроки, оцінити варіанти;
  * код — усі числа: ціни, частки, економія, порівняння товарів.

Тому на питання «звідки цифри?» відповідь завжди одна: їх порахував код,
модель їх лише використала для рішення.
"""
from __future__ import annotations

import json
from typing import Any

from app.llm.provider import ToolSpec
from app.mcp import tools as T
from app.nutrition import categories as cat
from app.nutrition.parser import parse_product
from app.nutrition.score import score_product


class AgentSession:
    """Стан однієї сесії агента: контекст магазину, кеш, чернетка кошика."""

    def __init__(self, api, ctx: T.CartContext, profile: dict[str, Any]) -> None:
        self.api = api
        self.ctx = ctx
        self.profile = profile
        self.products: dict[str, Any] = {}      # slug -> ProductInfo
        self.draft: list[dict[str, Any]] = []   # чернетка кошика
        self.history_cache: dict[str, Any] | None = None
        self.promo_cache: list[dict[str, Any]] | None = None

    # ---------------- інструменти ----------------

    async def get_profile(self) -> dict[str, Any]:
        """Ціль гостя, обмеження, бюджет."""
        return self.profile

    async def get_purchase_history(self) -> dict[str, Any]:
        """Структура покупок гостя за чеками: категорії, топ-товари, витрати."""
        if self.history_cache is not None:
            return self.history_cache

        from app.services.habits import fetch_offline_orders

        orders = await fetch_offline_orders(self.api, self.ctx)
        lines: list[dict[str, Any]] = []
        frequency: dict[str, dict[str, Any]] = {}
        for order in orders:
            for line in order.items:
                lines.append(line)
                name = line.get("name") or ""
                row = frequency.setdefault(name, {"name": name, "slug": line.get("slug"),
                                                  "times": 0, "price": line.get("price")})
                row["times"] += 1

        structure = cat.analyse(lines, self.profile.get("goal"))
        top = sorted(frequency.values(), key=lambda r: -r["times"])[:12]
        days = max((orders[0].created_at - orders[-1].created_at).days, 1) if len(orders) > 1 else 1

        self.history_cache = {
            "receipts": len(orders),
            "period_days": days,
            "total_spend": round(sum(o.total for o in orders), 2),
            "saved_on_promotions": round(sum(o.discount for o in orders), 2),
            "structure": structure.as_dict(),
            "top_products": top,
        }
        return self.history_cache

    async def get_promotions(self) -> dict[str, Any]:
        """Активні акції магазину та персональні купони гостя."""
        if self.promo_cache is not None:
            return {"promotions": self.promo_cache}
        promotions: list[dict[str, Any]] = []
        try:
            payload = await self.api.call(T.GET_PROMOTIONS, self.ctx.as_args(limit=10))
            if not T.is_mcp_error(payload) and isinstance(payload, dict):
                promotions = [
                    {"name": p.get("name") or p.get("title"), "code": p.get("code")}
                    for p in (payload.get("promotions") or [])[:10]
                ]
        except Exception:  # noqa: BLE001
            pass
        coupons: list[dict[str, Any]] = []
        try:
            payload = await self.api.call("silpo_get_my_coupons", {})
            if not T.is_mcp_error(payload) and isinstance(payload, dict):
                coupons = [
                    {"name": c.get("name") or c.get("title"), "value": c.get("valueText")}
                    for c in (payload.get("coupons") or [])[:10]
                ]
        except Exception:  # noqa: BLE001
            pass
        self.promo_cache = promotions
        return {"promotions": promotions, "personal_coupons": coupons}

    async def find_products(self, queries: list[str]) -> dict[str, Any]:
        """Пошук товарів у магазині гостя. До 20 назв за виклик."""
        payload = await self.api.call(
            T.FIND_PRODUCTS_BATCH, self.ctx.as_args(products=list(queries)[:20])
        )
        if T.is_mcp_error(payload):
            return {"error": "пошук недоступний", "products": []}

        results: list[dict[str, Any]] = []
        for block in (payload.get("queries") or []):
            for raw in (block.get("products") or [])[:4]:
                slug = raw.get("slug")
                if not slug or slug in self.products:
                    continue
                results.append({
                    "slug": slug,
                    "name": raw.get("name"),
                    "price": raw.get("price"),
                    "old_price": raw.get("oldPrice"),
                    "on_promotion": bool(raw.get("oldPrice") and raw.get("oldPrice") > raw.get("price", 0)),
                    "category": cat.categorize(raw.get("name") or ""),
                    "product_id": raw.get("id"),
                    "available": raw.get("available", True),
                })
        return {"found": len(results), "products": results[:24]}

    async def inspect_product(self, slug: str) -> dict[str, Any]:
        """Деталі товару: склад, алергени, харчова цінність, оцінка."""
        payload = await self.api.call(T.GET_PRODUCT_DETAILS, self.ctx.product_args(slug))
        if T.is_mcp_error(payload):
            return {"error": "товар недоступний"}
        product = parse_product(payload, fallback_slug=slug)
        self.products[slug] = product
        scored = score_product(product)
        return {
            "slug": slug, "name": product.title, "brand": product.brand,
            "price": product.price, "saved_if_bought_now": product.discount,
            "category": cat.categorize(product.title),
            "allergens": product.allergens_text,
            "nutrition_per_100g": {
                "kcal": product.nutrition.energy_kcal, "protein": product.nutrition.protein,
                "fat": product.nutrition.fat, "carbs": product.nutrition.carbs,
            },
            "score_0_100": scored.score,
            "note": scored.note,
        }

    async def add_to_draft(self, slug: str, quantity: int = 1, reason: str = "") -> dict[str, Any]:
        """Кладе товар у ЧЕРНЕТКУ кошика. У Сільпо нічого не пишеться."""
        product = self.products.get(slug)
        if product is None:
            detail = await self.inspect_product(slug)
            if detail.get("error"):
                return detail
            product = self.products.get(slug)

        existing = next((i for i in self.draft if i["slug"] == slug), None)
        if existing:
            existing["quantity"] += quantity
        else:
            self.draft.append({
                "slug": slug, "product_id": product.product_id, "name": product.title,
                "price": product.price or 0, "old_price": product.old_price or product.price or 0,
                "quantity": quantity, "category": cat.categorize(product.title),
                "image": product.image, "reason": reason,
                "on_promotion": product.on_promotion, "saved": product.discount,
            })
        return self.draft_summary()

    def draft_summary(self) -> dict[str, Any]:
        """Підсумок чернетки: сума, економія, структура, бюджет. Рахує код."""
        total = sum(i["price"] * i["quantity"] for i in self.draft)
        saved = sum(i["saved"] * i["quantity"] for i in self.draft)
        budget = self.profile.get("weekly_budget")
        structure = cat.analyse(
            [{"name": i["name"], "price": i["price"], "quantity": i["quantity"]} for i in self.draft],
            self.profile.get("goal"),
        )
        return {
            "items": len(self.draft),
            "total_price": round(total, 2),
            "saved_on_promotions": round(saved, 2),
            "budget": budget,
            "within_budget": (budget is None or total <= budget),
            "budget_left": round(budget - total, 2) if budget else None,
            "structure": structure.as_dict(),
        }

    async def get_draft(self) -> dict[str, Any]:
        """Поточна чернетка кошика з підсумками."""
        return {"draft": self.draft, "summary": self.draft_summary()}

    async def remove_from_draft(self, slug: str) -> dict[str, Any]:
        self.draft = [i for i in self.draft if i["slug"] != slug]
        return self.draft_summary()


def build_tools(session: AgentSession) -> list[ToolSpec]:
    """Опис інструментів для моделі. Свідомо мало й осмислено."""
    return [
        ToolSpec(
            name="get_profile",
            description="Ціль гостя, дієтичні обмеження, тижневий бюджет, кількість людей у домі.",
            parameters={"type": "object", "properties": {}},
            handler=session.get_profile,
        ),
        ToolSpec(
            name="get_purchase_history",
            description=(
                "Структура реальних покупок гостя за чеками Сільпо: частка витрат по "
                "категоріях із орієнтирами, топ-товари з частотою, сума витрат і "
                "економія на акціях. Головне джерело контексту — викликай першим."
            ),
            parameters={"type": "object", "properties": {}},
            handler=session.get_purchase_history,
        ),
        ToolSpec(
            name="get_promotions",
            description="Активні акції магазину гостя та його персональні купони.",
            parameters={"type": "object", "properties": {}},
            handler=session.get_promotions,
        ),
        ToolSpec(
            name="find_products",
            description=(
                "Шукає товари в магазині гостя за назвами (до 20 за виклик). "
                "Повертає ціну, стару ціну, ознаку акції та категорію. "
                "Пиши назви так, як на цінниках: «Вода мінеральна негазована»."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Назви товарів для пошуку",
                    }
                },
                "required": ["queries"],
            },
            handler=session.find_products,
        ),
        ToolSpec(
            name="inspect_product",
            description=(
                "Деталі конкретного товару: склад, алергени, харчова цінність і "
                "детермінована оцінка 0–100. Використовуй перед тим, як покласти "
                "товар у кошик, якщо потрібно порівняти варіанти."
            ),
            parameters={
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
            handler=session.inspect_product,
        ),
        ToolSpec(
            name="add_to_draft",
            description=(
                "Кладе товар у чернетку кошика. У Сільпо НІЧОГО не записується — "
                "це станеться лише після підтвердження гостем. Повертає підсумок: "
                "суму, економію, структуру категорій і залишок бюджету."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "quantity": {"type": "integer", "description": "Скільки упаковок"},
                    "reason": {"type": "string", "description": "Чому цей товар — одне речення"},
                },
                "required": ["slug"],
            },
            handler=session.add_to_draft,
        ),
        ToolSpec(
            name="get_draft",
            description="Поточна чернетка кошика з підсумками — перевір перед завершенням.",
            parameters={"type": "object", "properties": {}},
            handler=session.get_draft,
        ),
        ToolSpec(
            name="remove_from_draft",
            description="Прибирає товар із чернетки, якщо не влазить у бюджет або не підходить.",
            parameters={
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
            handler=session.remove_from_draft,
        ),
    ]
