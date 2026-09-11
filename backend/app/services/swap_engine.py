"""Двигун замін на правилах (без LLM).

Ланцюжок:
  1. Беремо проблемні товари — з чеків (повторювані) або з кошика.
  2. Правило (nutrition/rules.py) каже, ЩО шукати замість цього товару.
  3. silpo_find_products_batch знаходить кандидатів за назвами (до 30 за виклик).
  4. silpo_get_product_details дає харчову цінність кожного кандидата.
  5. Кандидат проходить, ЛИШЕ якщо його детермінований скор вищий на MIN_GAIN.
  6. Ранг: приріст балів + бонус за власну марку + бонус за акцію.

Тобто правила лише пропонують напрямок, рішення ухвалюють числа.
"""
from __future__ import annotations

from typing import Any

from app.db import repo
from app.mcp import tools as T
from app.nutrition.parser import ProductInfo, parse_product
from app.nutrition.rules import SwapRule, match_rule
from app.nutrition.score import ScoredItem, score_product
from app.services import pricing

MIN_GAIN = 10               # мінімальний приріст балів, щоб пропонувати заміну
MAX_TARGETS = 5             # скільки проблемних товарів опрацьовуємо за раз
MAX_CANDIDATES_PER_RULE = 6
OWN_BRAND_BONUS = 6
PROMO_BONUS = 8


def _candidate_products(payload: Any) -> list[dict[str, Any]]:
    """Витягує товари з відповіді silpo_find_products_batch."""
    if not isinstance(payload, dict):
        return []
    out: list[dict[str, Any]] = []
    # фактична схема: {"queries": [{"query": ..., "totalFound": N, "products": [...]}]}
    for key in ("queries", "results", "items", "searches"):
        for block in payload.get(key) or []:
            if isinstance(block, dict):
                out.extend(block.get("products") or [])
    out.extend(payload.get("products") or [])
    return [p for p in out if isinstance(p, dict) and p.get("slug")]


async def find_candidates(
    api,
    ctx: T.CartContext,
    rule: SwapRule,
    product=None,
    restrictions: list[str] | None = None,
    tolerance: Any = pricing.DEFAULT_TOLERANCE,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Кандидати на заміну: спершу запити від AI, потім статичні з правила.

    AI знає те, чого немає в каталозі — чим люди насправді замінюють колу чи
    чіпси. Але вибір робить не він: нижче кожен кандидат перевіряється
    детермінованим скором і ціною.
    """
    from app.llm import advisor

    ai = None
    queries = list(rule.queries)
    if product is not None:
        # Правило і поріг гостя обмежують ціну разом — перемагає суворіший
        ratio = pricing.combine(rule.max_price_ratio, tolerance)
        max_price = (product.price or 0) * ratio if product.price else None
        ai = await advisor.swap_queries(product, restrictions or [], max_price)
        if ai:
            queries = ai["queries"] + queries

    payload = await api.call("silpo_find_products_batch", ctx.as_args(products=queries[:30]))
    if T.is_mcp_error(payload):
        return [], ai
    return _candidate_products(payload), ai


async def best_replacement(
    api,
    ctx: T.CartContext,
    target: ScoredItem,
    rule: SwapRule,
    promo_slugs: set[str],
    product=None,
    restrictions: list[str] | None = None,
    tolerance: Any = pricing.DEFAULT_TOLERANCE,
) -> tuple[ProductInfo, ScoredItem, float, dict[str, Any] | None] | None:
    candidates, ai = await find_candidates(api, ctx, rule, product, restrictions, tolerance)
    seen: set[str] = set()
    best: tuple[float, ProductInfo, ScoredItem] | None = None

    for raw in candidates:
        slug = raw.get("slug")
        if not slug or slug in seen or slug == target.slug:
            continue
        seen.add(slug)
        if len(seen) > MAX_CANDIDATES_PER_RULE:
            break
        try:
            detail = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(slug))
        except Exception:  # noqa: BLE001
            continue
        if T.is_mcp_error(detail):
            continue
        info = parse_product(detail, fallback_slug=slug, fallback_title=raw.get("name") or "")
        if not info.has_nutrition:
            continue
        scored = score_product(info, target.quantity)
        if scored.score is None or target.score is None:
            continue
        gain = scored.score - target.score
        if gain < MIN_GAIN:
            continue
        # Ціна — критерій №1: поріг гостя відсікає кандидата раніше за все інше
        if not pricing.is_within(
            target.price, info.price, pricing.combine(rule.max_price_ratio, tolerance) - 1.0
        ):
            continue
        rank = (
            gain
            + (OWN_BRAND_BONUS if info.is_own_brand else 0)
            + (PROMO_BONUS if slug in promo_slugs or info.on_promotion else 0)
        )
        # productId потрібен для write-викликів
        info.product_id = info.product_id or str(raw.get("id") or "")
        if best is None or rank > best[0]:
            best = (rank, info, scored)

    if best is None:
        return None
    return best[1], best[2], best[0], ai


async def promo_slugs(api, ctx: T.CartContext) -> set[str]:
    """Слаги товарів, що зараз в акції — дають бонус до рангу заміни."""
    try:
        promos = await api.call("silpo_get_promotions", ctx.as_args(limit=5))
    except Exception:  # noqa: BLE001
        return set()
    if T.is_mcp_error(promos) or not isinstance(promos, dict):
        return set()
    codes = [
        p.get("code") or p.get("promotionCode")
        for p in (promos.get("promotions") or [])[:3]
        if isinstance(p, dict)
    ]
    slugs: set[str] = set()
    for code in [c for c in codes if c][:2]:
        try:
            products = await api.call(
                "silpo_get_products", ctx.as_args(promotionCode=code, limit=40)
            )
        except Exception:  # noqa: BLE001
            continue
        if T.is_mcp_error(products) or not isinstance(products, dict):
            continue
        for item in products.get("products") or []:
            if isinstance(item, dict) and item.get("slug"):
                slugs.add(item["slug"])
    return slugs


async def build(
    user_id: str,
    api,
    ctx: T.CartContext,
    targets: list[tuple[ScoredItem, dict[str, Any]]],
    restrictions: list[str] | None = None,
    tolerance: Any = pricing.DEFAULT_TOLERANCE,
) -> list[dict[str, Any]]:
    """targets — пари (оцінений товар, контекст: скільки разів куплено / чи в кошику)."""
    prioritized = [t for t in targets if t[0].score is not None]
    prioritized.sort(key=lambda t: (t[0].score, -t[1].get("times", 1)))
    prioritized = prioritized[:MAX_TARGETS]
    if not prioritized:
        return []

    promos = await promo_slugs(api, ctx)
    suggestions: list[dict[str, Any]] = []

    for target, meta in prioritized:
        rule = meta.get("rule")
        if rule is None:
            continue
        found = await best_replacement(
            api, ctx, target, rule, promos,
            product=meta.get("product"), restrictions=restrictions or [],
            tolerance=tolerance,
        )
        if not found:
            continue
        info, scored, _rank, ai = found
        suggestions.append(
            {
                "cart_id": ctx.cart_id if meta.get("in_cart") else None,
                "original_product_id": target.product_id or target.slug,
                "original_title": target.title,
                "suggested_product_id": info.product_id or info.slug,
                "suggested_title": info.title,
                "score_delta": round((scored.score or 0) - (target.score or 0), 1),
                "is_own_brand": info.is_own_brand,
                "reason": (
                    (ai or {}).get("reason")
                    or f"{rule.title.lower()} → {rule.reason}. "
                       f"{target.score} → {scored.score} балів"
                ),
                "_meta": {
                    "rule": rule.key,
                    "problem": (ai or {}).get("problem") or rule.title,
                    "ai_used": bool(ai),
                    "saved": info.discount,
                    "on_promotion": info.on_promotion,
                    "tags": rule.tags,
                    "original_slug": target.slug,
                    "original_score": target.score,
                    "original_image": target.image,
                    "original_price": target.price,
                    "suggested_slug": info.slug,
                    "suggested_score": scored.score,
                    "suggested_image": info.image,
                    "suggested_price": info.price,
                    "on_promotion": info.slug in promos,
                    "times_bought": meta.get("times", 1),
                    "in_cart": bool(meta.get("in_cart")),
                    "external_product_id": meta.get("external_product_id"),
                },
            }
        )

    stored = await repo.save_swap_suggestions(
        user_id, [{k: v for k, v in s.items() if k != "_meta"} for s in suggestions]
    )
    for saved, source in zip(stored, suggestions):
        saved.update(source["_meta"])
    return stored


def targets_from_habits(top_products: list[dict[str, Any]], details: dict[str, ProductInfo]):
    """Проблемні товари зі звичок: часто купуються і мають правило заміни."""
    out: list[tuple[ScoredItem, dict[str, Any]]] = []
    for row in top_products:
        product = details.get(row.get("slug"))
        if product is None:
            continue
        rule = match_rule(product)
        if rule is None:
            continue
        scored = score_product(product)
        out.append((scored, {
            "rule": rule, "times": row.get("times", 1), "in_cart": False,
            "product": product,
        }))
    return out
