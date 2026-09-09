"""Звички покупця з офлайн-чеків Сільпо.

silpo_get_my_online_orders у більшості гостей порожній (доставку замовляють
рідко), а реальні покупки лежать в silpo_get_my_offline_orders — там дата,
сума, знижка і повний список товарів із catalogProduct.slug.

Рахуємо:
  * тижневий тренд оцінки (weekly_snapshots) — по датах чеків;
  * топ-товари, які купуються регулярно;
  * частку витрат на категорії-маркери (солодке, алкоголь, готова їжа);
  * середній чек і частоту походів у магазин.

Щоб не впертись у rate limit, харчову цінність тягнемо лише для найчастіших
товарів (MAX_DETAIL_SLUGS) і кешуємо в межах виклику.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.db import repo
from app.mcp import tools as T
from app.nutrition.parser import ProductInfo, parse_product, parse_weight_grams
from app.nutrition.score import score_basket, score_product

PAGE_SIZE = 10          # жорсткий максимум silpo_get_my_offline_orders
MAX_ORDERS = 20
MAX_DETAIL_SLUGS = 22

# Маркери категорій для «звичок» — за назвою товару (каталог не віддає категорію)
CATEGORY_MARKERS: dict[str, tuple[str, ...]] = {
    "Солодке й снеки": ("шоколад", "цукерк", "печив", "вафл", "морозиво", "батончик",
                        "чіпс", "снек", "круасан", "тістечк", "торт", "десерт", "пряник"),
    "Солодкі напої": ("кола", "cola", "pepsi", "фанта", "спрайт", "energy", "енергетик",
                      "лимонад", "нектар", "сік ", "напій"),
    "Алкоголь": ("пиво", "вино", "віскі", "горілк", "лікер", "сидр", "коньяк", "шампан", "beer"),
    "Мʼясо й риба": ("філе", "куряч", "свинин", "яловичин", "фарш", "риба", "лосос",
                     "оселедець", "ковбас", "сосиск", "бекон", "шинк"),
    "Овочі й фрукти": ("огірок", "помідор", "яблук", "банан", "капуст", "морква", "цибул",
                       "картопл", "салат", "зелень", "ягод", "апельсин", "лимон", "авокадо"),
    "Молочне": ("молоко", "йогурт", "сир", "кефір", "сметан", "вершк", "масло"),
    "Хліб і крупи": ("хліб", "багет", "булочк", "крупа", "рис", "гречк", "макарон",
                     "паста", "борошн", "пластівц", "мюслі"),
}


def categorize(name: str) -> str:
    low = (name or "").lower()
    for category, markers in CATEGORY_MARKERS.items():
        if any(m in low for m in markers):
            return category
    return "Інше"


def week_start(value: Any) -> date | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    d = dt.date()
    return d - timedelta(days=d.weekday())


@dataclass
class OfflineOrder:
    created_at: datetime
    total: float
    discount: float
    branch: str
    items: list[dict[str, Any]]


def parse_orders(payload: Any) -> list[OfflineOrder]:
    orders: list[OfflineOrder] = []
    for raw in (payload or {}).get("orders", []) if isinstance(payload, dict) else []:
        try:
            created = datetime.fromisoformat(str(raw.get("createdAt")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        orders.append(
            OfflineOrder(
                created_at=created,
                total=float(raw.get("sumReg") or 0),
                discount=float(raw.get("sumDiscount") or 0),
                branch=str(raw.get("filialName") or ""),
                items=T.offline_order_items(raw),
            )
        )
    return orders


async def fetch_offline_orders(api, ctx: T.CartContext, limit: int = MAX_ORDERS) -> list[OfflineOrder]:
    """Чеки з пагінацією: MCP віддає максимум 10 за виклик."""
    orders: list[OfflineOrder] = []
    for offset in range(0, limit, PAGE_SIZE):
        payload = await api.call(
            T.GET_OFFLINE_ORDERS, ctx.as_args(limit=PAGE_SIZE, offset=offset)
        )
        if T.is_mcp_error(payload):
            break
        page = parse_orders(payload)
        orders.extend(page)
        if len(page) < PAGE_SIZE:
            break
    return orders


async def load_details_for(api, ctx: T.CartContext, slugs: list[str]) -> dict[str, ProductInfo]:
    out: dict[str, ProductInfo] = {}
    for slug in slugs[:MAX_DETAIL_SLUGS]:
        if not slug or slug in out:
            continue
        try:
            payload = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(slug))
        except Exception:  # noqa: BLE001
            continue
        if T.is_mcp_error(payload):
            continue
        out[slug] = parse_product(payload, fallback_slug=slug)
    return out


def _line_grams(line: dict[str, Any]) -> float | None:
    return parse_weight_grams(line.get("unit"))


async def build(user_id: str, api, ctx: T.CartContext) -> dict[str, Any]:
    """Повний аналіз звичок + запис тижневих зрізів у Supabase."""
    orders = await fetch_offline_orders(api, ctx)
    if not orders:
        return {"orders_count": 0, "weeks": [], "top_products": [], "categories": [], "summary": None}

    frequency = Counter()
    names: dict[str, str] = {}
    for order in orders:
        for line in order.items:
            if line.get("slug"):
                frequency[line["slug"]] += line.get("quantity") or 1
                names.setdefault(line["slug"], line.get("name") or line["slug"])

    details = await load_details_for(api, ctx, [s for s, _ in frequency.most_common()])

    # --- тижневі зрізи ---
    by_week: dict[date, list[dict[str, Any]]] = defaultdict(list)
    spend_by_week: dict[date, float] = defaultdict(float)
    for order in orders:
        wk = week_start(order.created_at.isoformat())
        if wk is None:
            continue
        by_week[wk].extend(order.items)
        spend_by_week[wk] += order.total

    weeks: list[dict[str, Any]] = []
    for wk in sorted(by_week):
        scored = []
        for line in by_week[wk]:
            product = details.get(line.get("slug"))
            if product is None:
                continue
            item = score_product(product, line.get("quantity") or 1)
            grams = _line_grams(line)
            if grams:
                item.grams = grams * (line.get("quantity") or 1)
            scored.append(item)
        basket = score_basket(scored)
        if basket.covered_items == 0:
            continue   # тиждень без жодного товару з харчовою цінністю — не малюємо нуль
        snapshot = {
            "week_start_date": wk.isoformat(),
            "avg_calories": round(basket.totals.get("calories", 0) / 7, 1),
            "avg_protein": round(basket.totals.get("protein", 0) / 7, 1),
            "avg_fat": round(basket.totals.get("fat", 0) / 7, 1),
            "avg_carbs": round(basket.totals.get("carbs", 0) / 7, 1),
            "total_added_sugar": None,   # каталог Сільпо не віддає цукор
            "health_score": basket.score,
            "source": "offline_orders",
        }
        await repo.upsert_weekly_snapshot(user_id, snapshot)
        weeks.append({**snapshot, "spend": round(spend_by_week[wk], 2), "shares": basket.shares})

    # --- профіль: оцінка ТИПОВОГО раціону за всіма чеками ---
    all_scored = []
    for order in orders:
        for line in order.items:
            product = details.get(line.get("slug"))
            if product is None:
                continue
            item = score_product(product, line.get("quantity") or 1)
            grams = _line_grams(line)
            if grams:
                item.grams = grams * (line.get("quantity") or 1)
            all_scored.append(item)
    profile_basket = score_basket(all_scored)
    profile = {
        "score": profile_basket.score,
        "letter": profile_basket.letter,
        "shares": profile_basket.shares,
        "deviations": profile_basket.deviations,
        "energy_density": profile_basket.energy_density,
        "totals": profile_basket.totals,
        "coverage": {
            "covered": profile_basket.covered_items,
            "skipped": profile_basket.skipped_items,
            "pct": profile_basket.coverage_pct,
        },
        "methodology": profile_basket.methodology,
    } if profile_basket.covered_items else None

    # --- топ-товари й категорії ---
    top_products = [
        {
            "slug": slug,
            "title": names.get(slug, slug),
            "times": count,
            "score": (details[slug] and score_product(details[slug]).score) if slug in details else None,
            "image": details[slug].image if slug in details else None,
        }
        for slug, count in frequency.most_common(8)
    ]

    spend_by_category: Counter = Counter()
    count_by_category: Counter = Counter()
    for order in orders:
        for line in order.items:
            category = categorize(line.get("name") or "")
            spend_by_category[category] += (line.get("price") or 0) * (line.get("quantity") or 1)
            count_by_category[category] += line.get("quantity") or 1
    total_spend = sum(spend_by_category.values()) or 1

    categories = [
        {
            "name": name,
            "spend": round(value, 2),
            "share": round(value / total_spend * 100, 1),
            "items": count_by_category[name],
        }
        for name, value in spend_by_category.most_common()
    ]

    span_days = max((orders[0].created_at - orders[-1].created_at).days, 1) if len(orders) > 1 else 1
    summary = {
        "orders_count": len(orders),
        "period_days": span_days,
        "avg_check": round(sum(o.total for o in orders) / len(orders), 2),
        "total_spend": round(sum(o.total for o in orders), 2),
        "total_saved": round(sum(o.discount for o in orders), 2),
        "visits_per_week": round(len(orders) / max(span_days / 7, 1), 1),
        "favourite_branch": Counter(o.branch for o in orders).most_common(1)[0][0],
        "last_visit": orders[0].created_at.date().isoformat(),
    }

    return {
        "orders_count": len(orders),
        "profile": profile,
        "weeks": weeks,
        "top_products": top_products,
        "categories": categories,
        "summary": summary,
    }
