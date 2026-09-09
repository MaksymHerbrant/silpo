"""План наступної покупки — ядро продукту.

Обіцянка: перетворити історію покупок на розумні рішення для наступної покупки.

Не «ось твоя статистика» і не «ось правильний кошик», а конкретний перелік
рішень щодо ТВОГО звичного набору: що лишити, що замінити, що додати.

Три причини, чому це корисно, і всі три живуть в одному списку:
  💰 зекономити    — акції на те, що ти й так береш, вигідніші аналоги
  🥗 трохи краще   — ОДНА конкретна зміна в реальному товарі, не мораль
  🧠 менше зусиль  — звичний кошик уже зібраний, лишилось підтвердити

Health свідомо не є головним числом. Жодного «Health Score 74/100», який
доводиться захищати. Натомість одне спостереження, прив'язане до конкретної
покупки, з конкретною альтернативою і різницею в ціні.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.mcp import tools as T
from app.nutrition import categories as cats
from app.nutrition.parser import ProductInfo, parse_product
from app.nutrition.rules import match_rule
from app.services import insights

# Дії, які гість може прийняти щодо позиції свого звичного набору
ACTION_KEEP = "keep"        # лишити як є
ACTION_SWITCH = "switch"    # замінити на знайдену альтернативу
ACTION_ADD = "add"          # докупити (акція на те, що зазвичай береш)
ACTION_REVIEW = "review"    # варте уваги: подорожчало або є вигідніший аналог

MAX_ALTERNATIVE_LOOKUPS = 3
MAX_CANDIDATES = 4
MIN_SAVING = 5.0            # менша різниця в ціні не варта уваги гостя
MAX_PRICE_RATIO = 1.15      # альтернатива не може бути помітно дорожчою
MIN_PRICE_RATIO = 0.5       # удвічі дешевше — це вже інший формат товару
MAX_WEIGHT_RATIO = 2.5      # і за вагою упаковки не має відрізнятись у рази

# Слова, які означають ІНШИЙ продукт, навіть коли назва схожа.
# «Банан» і «банан сушений» — не одне й те саме.
DIFFERENT_FORM = (
    "сушен", "в'ялен", "вялен", "заморож", "консерв", "маринован", "копчен",
    "концентрат", "порошок", "сироп", "паста", "чипси", "снек", "сухофрукт",
)


@dataclass
class PlanItem:
    slug: str
    product_id: str
    name: str
    image: str | None
    price: float
    quantity: int
    category: str
    times_bought: int
    action: str = ACTION_KEEP
    note: str = ""
    saved: float = 0.0
    on_promotion: bool = False
    old_price: float | None = None
    alternative: dict[str, Any] | None = None
    selected: bool = True          # у плані за замовчуванням, гість може зняти

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug, "product_id": self.product_id, "name": self.name,
            "image": self.image, "price": self.price, "quantity": self.quantity,
            "category": self.category, "category_label": cats.CATEGORY_LABELS.get(self.category, ""),
            "times_bought": self.times_bought, "action": self.action, "note": self.note,
            "saved": round(self.saved, 2), "on_promotion": self.on_promotion,
            "old_price": self.old_price, "alternative": self.alternative,
            "selected": self.selected,
            "line_total": round(self.price * self.quantity, 2),
        }


@dataclass
class Finding:
    kind: str          # promo | health | alternative | usual
    title: str
    value: str
    detail: str = ""
    slugs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "title": self.title, "value": self.value,
            "detail": self.detail, "slugs": self.slugs,
        }


async def _find_alternatives(
    api, ctx: T.CartContext, product: ProductInfo, queries: list[str]
) -> list[tuple[ProductInfo, float]]:
    """Шукає дешевші аналоги тієї самої ролі. Повертає (товар, скільки економить)."""
    payload = await api.call(T.FIND_PRODUCTS_BATCH, ctx.as_args(products=queries[:12]))
    if T.is_mcp_error(payload) or not isinstance(payload, dict):
        return []

    out: list[tuple[ProductInfo, float]] = []
    seen: set[str] = set()
    for block in payload.get("queries") or []:
        for raw in (block.get("products") or [])[:MAX_CANDIDATES]:
            slug = raw.get("slug")
            if not slug or slug == product.slug or slug in seen:
                continue
            seen.add(slug)
            price = raw.get("price")
            if not price or not product.price:
                continue
            if price > product.price * MAX_PRICE_RATIO:
                continue
            try:
                detail = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(slug))
            except Exception:  # noqa: BLE001
                continue
            if T.is_mcp_error(detail):
                continue
            candidate = parse_product(detail, fallback_slug=slug, fallback_title=raw.get("name") or "")
            candidate.product_id = candidate.product_id or str(raw.get("id") or "")
            if not candidate.price or not _same_product_kind(product, candidate):
                continue
            out.append((candidate, round(product.price - candidate.price, 2)))
    return out


def _same_product_kind(original: ProductInfo, candidate: ProductInfo) -> bool:
    """Чи це справді той самий тип товару, а не інший формат.

    Без цієї перевірки свіжий банан за 72 ₴ «замінюється» сушеним за 26 ₴:
    формально дешевше, по суті — інший продукт.
    """
    if cats.categorize(candidate.title) != cats.categorize(original.title):
        return False

    original_low = original.title.lower()
    candidate_low = candidate.title.lower()
    for marker in DIFFERENT_FORM:
        if (marker in candidate_low) != (marker in original_low):
            return False

    if original.price and candidate.price:
        if candidate.price < original.price * MIN_PRICE_RATIO:
            return False

    if original.weight_g and candidate.weight_g:
        ratio = candidate.weight_g / original.weight_g
        if ratio > MAX_WEIGHT_RATIO or ratio < 1 / MAX_WEIGHT_RATIO:
            return False

    return True


def _health_candidate(items: list[dict[str, Any]], products: dict[str, ProductInfo]):
    """Обирає ОДИН товар для здоровішої заміни — той, що найчастіше купується
    і має правило покращення. Одне спостереження, а не список претензій."""
    best = None
    for item in items:
        product = products.get(item["slug"])
        if product is None:
            continue
        rule = match_rule(product)
        if rule is None:
            continue
        weight = item.get("times_bought", 1)
        if best is None or weight > best[0]:
            best = (weight, product, rule, item)
    return best


async def build(api, ctx: T.CartContext, orders, goal: str | None = None) -> dict[str, Any]:
    """Складає план наступної покупки зі знахідками."""
    usual = await insights.usual_basket(api, ctx, orders)
    raw_items = usual.get("items") or []
    if not raw_items:
        return {"has_data": False, "reason": usual.get("reason", "Замало чеків для плану")}

    # Деталі вже підтягнуті всередині usual_basket — перечитуємо лише те,
    # що знадобиться для правил заміни.
    products: dict[str, ProductInfo] = {}
    for item in raw_items[:12]:
        try:
            payload = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(item["slug"]))
        except Exception:  # noqa: BLE001
            continue
        if not T.is_mcp_error(payload):
            products[item["slug"]] = parse_product(payload, fallback_slug=item["slug"])

    plan: list[PlanItem] = []
    for item in raw_items:
        plan.append(PlanItem(
            slug=item["slug"], product_id=item["product_id"], name=item["name"],
            image=item.get("image"), price=item.get("price") or 0,
            quantity=item.get("quantity", 1), category=item.get("category", "other"),
            times_bought=item.get("times_bought", 1),
            on_promotion=item.get("on_promotion", False),
            old_price=item.get("old_price"), saved=item.get("saved") or 0,
        ))

    findings: list[Finding] = []

    # --- 💰 акції на те, що гість і так бере ---
    promos = [p for p in plan if p.on_promotion and p.saved > 0]
    for row in promos:
        row.action = ACTION_ADD
        row.note = f"зараз в акції, −{round(row.saved)} ₴"
    if promos:
        total = sum(p.saved * p.quantity for p in promos)
        findings.append(Finding(
            kind="promo",
            title=f"{len(promos)} ваші звичні товари в акції",
            value=f"−{round(total)} ₴",
            detail="Те, що ви й так берете, зараз дешевше",
            slugs=[p.slug for p in promos],
        ))

    # --- 🥗 одна конкретна зміна на краще ---
    health = _health_candidate(
        [p.as_dict() for p in plan], products
    )
    health_slug: str | None = None
    if health:
        _weight, product, rule, item = health
        alternatives = await _find_alternatives(api, ctx, product, rule.queries)
        if alternatives:
            best, saving = max(alternatives, key=lambda x: x[1])
            row = next((p for p in plan if p.slug == product.slug), None)
            if row is not None:
                row.action = ACTION_SWITCH
                row.alternative = {
                    "slug": best.slug, "product_id": best.product_id, "name": best.title,
                    "price": best.price, "image": best.image, "saved": saving,
                    "on_promotion": best.on_promotion,
                    "why": rule.reason,
                }
                row.note = rule.title.lower()
                health_slug = row.slug
                price_note = (
                    f"і на {round(saving)} ₴ дешевше" if saving >= MIN_SAVING
                    else "за схожою ціною"
                )
                findings.append(Finding(
                    kind="health",
                    title="Одна проста зміна",
                    value=best.title,
                    detail=(
                        f"Ви регулярно берете «{product.title}». "
                        f"Знайшов схожий варіант — {rule.reason}, {price_note}."
                    ),
                    slugs=[row.slug],
                ))

    # --- 🔄 вигідніші аналоги для решти ---
    cheaper: list[PlanItem] = []
    checked = 0
    for row in plan:
        if checked >= MAX_ALTERNATIVE_LOOKUPS:
            break
        if row.slug == health_slug or row.action != ACTION_KEEP:
            continue
        product = products.get(row.slug)
        if product is None or not product.price or product.price < 30:
            continue
        checked += 1
        alternatives = await _find_alternatives(api, ctx, product, [product.title])
        if not alternatives:
            continue
        best, saving = max(alternatives, key=lambda x: x[1])
        if saving < MIN_SAVING:
            continue
        row.action = ACTION_REVIEW
        row.note = f"є аналог на {round(saving)} ₴ дешевше"
        row.alternative = {
            "slug": best.slug, "product_id": best.product_id, "name": best.title,
            "price": best.price, "image": best.image, "saved": saving,
            "on_promotion": best.on_promotion, "why": "той самий товар, дешевше",
        }
        cheaper.append(row)

    if cheaper:
        total = sum((r.alternative or {}).get("saved", 0) * r.quantity for r in cheaper)
        findings.append(Finding(
            kind="alternative",
            title=f"{len(cheaper)} вигідніші аналоги",
            value=f"−{round(total)} ₴",
            detail="Той самий товар, але дешевше",
            slugs=[r.slug for r in cheaper],
        ))

    total_price = sum(p.price * p.quantity for p in plan)
    findings.append(Finding(
        kind="usual",
        title="Звичний кошик готовий",
        value=f"{len(plan)} товарів · {round(total_price)} ₴",
        detail=f"Зібрано з ваших покупок за {usual.get('based_on_weeks')} тижнів",
    ))

    return {
        "has_data": True,
        "items": [p.as_dict() for p in plan],
        "findings": [f.as_dict() for f in findings],
        "summary": {
            "items": len(plan),
            "total_price": round(total_price, 2),
            "promo_savings": round(sum(p.saved * p.quantity for p in promos), 2),
            "alternative_savings": round(
                sum((r.alternative or {}).get("saved", 0) * r.quantity for r in cheaper), 2
            ),
            "based_on_weeks": usual.get("based_on_weeks"),
        },
    }
