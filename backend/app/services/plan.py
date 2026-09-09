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
from app.nutrition import allergens as al
from app.nutrition import categories as cats
from app.nutrition.parser import ProductInfo, parse_product
from app.nutrition.rules import match_rule
from app.services import noise as noise_filter
from app.services import profile as profile_service

# Дії, які гість може прийняти щодо позиції свого звичного набору
ACTION_KEEP = "keep"        # лишити як є
ACTION_SWITCH = "switch"    # замінити на знайдену альтернативу
ACTION_ADD = "add"          # докупити (акція на те, що зазвичай береш)
ACTION_REVIEW = "review"    # варте уваги: подорожчало або є вигідніший аналог
ACTION_BLOCKED = "blocked"  # конфліктує з обмеженнями гостя — не пропонуємо

MAX_ALTERNATIVE_LOOKUPS = 3
MAX_CANDIDATES = 4
MIN_SAVING = 5.0            # менша різниця в ціні не варта уваги гостя
MAX_PRICE_RATIO = 1.15      # альтернатива не може бути помітно дорожчою

# Товар із довгим циклом не потрібен щотижня. Туалетний папір і джин у
# тижневому кошику виглядають абсурдно — тому позначаємо ритм покупки
# і групуємо список, а не робимо вигляд, що це щотижневі витрати.
CADENCE_BY_CYCLE = (
    (10, "weekly", "щотижня"),
    (20, "biweekly", "раз на два тижні"),
    (10 ** 6, "monthly", "раз на місяць"),
)


def cadence_for(cycle_days: int) -> tuple[str, str]:
    for limit, key, label in CADENCE_BY_CYCLE:
        if cycle_days <= limit:
            return key, label
    return "monthly", "раз на місяць"
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
    kind: str = "regular"           # regular | companion
    kind_reason: str = ""
    cadence: str = "weekly"         # weekly | biweekly | monthly
    cadence_label: str = ""
    cycle_days: int = 7
    allergen_hits: list[dict[str, Any]] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
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
            "kind": self.kind, "kind_reason": self.kind_reason,
            "cadence": self.cadence, "cadence_label": self.cadence_label,
            "cycle_days": self.cycle_days,
            "allergen_hits": self.allergen_hits,
            "detail": self.detail,
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


def _aggregate(orders) -> list[dict[str, Any]]:
    """Зводить чеки до агрегатів по товарах: скільки разів, на скільки грошей."""
    rows: dict[str, dict[str, Any]] = {}
    for order in orders:
        for line in order.items:
            slug = line.get("slug")
            if not slug:
                continue
            row = rows.setdefault(slug, {
                "slug": slug, "name": line.get("name"), "times": 0, "total_qty": 0.0,
                "spend": 0.0, "image": line.get("image"), "history": [],
            })
            qty = float(line.get("quantity") or 1)
            price = float(line.get("price") or 0)
            row["times"] += 1
            row["total_qty"] += qty
            row["spend"] += price * qty
            row["history"].append({
                "date": order.created_at.date().isoformat(),
                "price": price, "quantity": qty, "branch": order.branch,
            })
    return list(rows.values())


async def build(api, ctx: T.CartContext, orders, goal: str | None = None) -> dict[str, Any]:
    """Складає план наступної покупки: профіль, фільтр шуму, знахідки."""
    if not orders:
        return {"has_data": False, "reason": "Чеків Сільпо поки не знайшли"}

    guest = await profile_service.load(api)
    restrictions = guest.get("restriction_objects") or []

    period_days = (
        max((orders[0].created_at - orders[-1].created_at).days, 1) if len(orders) > 1 else 7
    )
    rows = _aggregate(orders)
    split = noise_filter.split(rows, receipts=len(orders), period_days=period_days)
    if not split["basket"]:
        return {"has_data": False, "reason": "У чеках немає товарів, які повторюються"}

    weeks = max(
        ((orders[0].created_at - orders[-1].created_at).days or 7) / 7, 1
    )

    # --- деталі товарів набору: ціна зараз, склад, алергени ---
    plan: list[PlanItem] = []
    products: dict[str, ProductInfo] = {}
    for row in split["basket"][:14]:
        try:
            payload = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(row["slug"]))
        except Exception:  # noqa: BLE001
            continue
        if T.is_mcp_error(payload):
            continue
        product = parse_product(payload, fallback_slug=row["slug"], fallback_title=row["name"] or "")
        products[row["slug"]] = product

        cycle_days = int(row.get("cycle_days") or 7)
        cadence, cadence_label = cadence_for(cycle_days)
        # Кількість рахуємо на ЦИКЛ товару, а не завжди на тиждень
        cycles = max(period_days / cycle_days, 1)
        per_cycle = max(round(row["total_qty"] / cycles), 1)
        item = PlanItem(
            slug=product.slug, product_id=product.product_id, name=product.title,
            image=product.image or row.get("image"), price=product.price or 0,
            quantity=per_cycle, category=cats.categorize(product.title),
            times_bought=row["times"], kind=row["kind"], kind_reason=row["kind_reason"],
            cadence=cadence, cadence_label=cadence_label, cycle_days=cycle_days,
            on_promotion=product.on_promotion, old_price=product.old_price,
            saved=product.discount,
        )

        # --- перевірка за профілем: алерген блокує, вподобання пропонує заміну ---
        hits = al.check_product(product, restrictions)
        if hits:
            item.allergen_hits = [
                {
                    "restriction": h.restriction, "matched": h.matched_text,
                    "severity": h.severity, "kind": h.kind, "action": h.action,
                }
                for h in hits
            ]
            blocking_hits = al.blocking(hits)
            swap_hits = al.swap_worthy(hits)
            if blocking_hits:
                item.action = ACTION_BLOCKED
                item.selected = False
                item.note = f"алерген у складі: {blocking_hits[0].restriction.lower()}"
            elif swap_hits:
                # Не блокуємо: гість сам вирішить, чи міняти
                item.note = f"у профілі: без «{swap_hits[0].restriction.lower()}»"

        item.detail = {
            "history": row["history"][:10],
            "times_bought": row["times"],
            "total_spend": round(row["spend"], 2),
            "avg_price": round(row["spend"] / max(row["total_qty"], 1), 2),
            "why": row["kind_reason"],
            "ingredients": product.ingredients,
            "allergens_text": product.allergens_text,
            "brand": product.brand,
            "country": product.country,
            "nutrition": {
                "kcal": product.nutrition.energy_kcal, "protein": product.nutrition.protein,
                "fat": product.nutrition.fat, "carbs": product.nutrition.carbs,
            },
            "allergen_check": (
                "Конфліктів із вашим профілем не знайдено" if not hits
                else "Знайдено конфлікт із обмеженнями профілю"
            ) if restrictions else "Обмеження в профілі не вказані",
        }
        plan.append(item)

    findings: list[Finding] = []

    # --- 🛡️ безпечні аналоги для заблокованих позицій ---
    blocked = [p for p in plan if p.action == ACTION_BLOCKED]
    preference_swaps = [
        p for p in plan
        if p.action != ACTION_BLOCKED
        and any(h.get("action") == "swap" for h in p.allergen_hits)
    ]
    for row in blocked:
        product = products.get(row.slug)
        if product is None:
            continue
        alternatives = await _find_alternatives(api, ctx, product, [product.title])
        safe = None
        for candidate, saving in alternatives:
            if not al.blocking(al.check_product(candidate, restrictions)):
                safe = (candidate, saving)
                break
        if safe:
            candidate, saving = safe
            row.alternative = {
                "slug": candidate.slug, "product_id": candidate.product_id,
                "name": candidate.title, "price": candidate.price, "image": candidate.image,
                "saved": saving, "on_promotion": candidate.on_promotion,
                "why": "без вашого алергену",
            }
    if blocked:
        found = sum(1 for b in blocked if b.alternative)
        findings.append(Finding(
            kind="safety",
            title=f"{len(blocked)} позиції з вашим алергеном",
            value=f"{found} безпечні заміни" if found else "перевірте склад",
            detail="У складі знайдено те, що ви вказали в профілі Сільпо як алерген",
            slugs=[b.slug for b in blocked],
        ))

    # --- 🎯 заміни за вподобанням із профілю (цукор у солодких напоях тощо) ---
    for row in preference_swaps:
        product = products.get(row.slug)
        if product is None or row.alternative:
            continue
        rule = match_rule(product)
        queries = rule.queries if rule else [product.title]
        alternatives = await _find_alternatives(api, ctx, product, queries)
        clean = [
            (c, s_)
            for c, s_ in alternatives
            if not al.check_product(c, restrictions)
        ]
        if not clean:
            continue
        best, saving = max(clean, key=lambda x: x[1])
        row.action = ACTION_SWITCH
        row.alternative = {
            "slug": best.slug, "product_id": best.product_id, "name": best.title,
            "price": best.price, "image": best.image, "saved": saving,
            "on_promotion": best.on_promotion,
            "why": f"відповідає вашому «{row.allergen_hits[0]['restriction'].lower()}»",
        }
    matched_swaps = [p for p in preference_swaps if p.alternative]
    if matched_swaps:
        findings.append(Finding(
            kind="preference",
            title=f"{len(matched_swaps)} позиції під ваші вподобання",
            value="є чисті варіанти",
            detail=(
                "Обмеження з профілю діє в категоріях, де це суть продукту — "
                "напої та солодощі. Хліб і молочку не чіпаємо."
            ),
            slugs=[p.slug for p in matched_swaps],
        ))

    # --- 💰 акції на те, що гість і так бере ---
    promos = [p for p in plan if p.on_promotion and p.saved > 0 and p.action == ACTION_KEEP]
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
        [p.as_dict() for p in plan if p.action == ACTION_KEEP and not p.alternative], products
    )
    health_slug: str | None = None
    if health:
        _weight, product, rule, _item = health
        alternatives = await _find_alternatives(api, ctx, product, rule.queries)
        safe = [(c, s) for c, s in alternatives if not al.check_product(c, restrictions)]
        if safe:
            best, saving = max(safe, key=lambda x: x[1])
            row = next((p for p in plan if p.slug == product.slug), None)
            if row is not None:
                row.action = ACTION_SWITCH
                row.alternative = {
                    "slug": best.slug, "product_id": best.product_id, "name": best.title,
                    "price": best.price, "image": best.image, "saved": saving,
                    "on_promotion": best.on_promotion, "why": rule.reason,
                }
                row.note = rule.title.lower()
                health_slug = row.slug
                price_note = (
                    f"і на {round(saving)} ₴ дешевше" if saving >= MIN_SAVING else "за схожою ціною"
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

    # --- 🔄 вигідніші аналоги ---
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
        safe = [(c, s) for c, s in alternatives if not al.check_product(c, restrictions)]
        if not safe:
            continue
        best, saving = max(safe, key=lambda x: x[1])
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

    # --- 🧹 звіт про відсіяний шум ---
    if split["filtered_count"]:
        findings.append(Finding(
            kind="noise",
            title=f"Відсіяно {split['filtered_count']} випадкові позиції",
            value=f"{round(split['filtered_spend'])} ₴",
            detail="Разові покупки не входять у звичний набір",
            slugs=[r["slug"] for r in split["noise"][:8]],
        ))

    active = [p for p in plan if p.action != ACTION_BLOCKED]
    total_price = sum(p.price * p.quantity for p in active)
    weekly_price = sum(p.price * p.quantity for p in active if p.cadence == "weekly")
    periodic_price = total_price - weekly_price

    return {
        "has_data": True,
        "profile": {
            "name": guest.get("name"),
            "restrictions": guest.get("restrictions"),
            "status": profile_service.status_line(guest),
        },
        "items": [p.as_dict() for p in plan],
        "findings": [f.as_dict() for f in findings],
        "noise": [
            {"name": r["name"], "spend": round(r["spend"], 2), "reason": r["kind_reason"]}
            for r in split["noise"][:10]
        ],
        "summary": {
            "items": len(active),
            "blocked": len(blocked),
            "total_price": round(total_price, 2),
            "weekly_price": round(weekly_price, 2),
            "periodic_price": round(periodic_price, 2),
            "promo_savings": round(sum(p.saved * p.quantity for p in promos), 2),
            "alternative_savings": round(
                sum((r.alternative or {}).get("saved", 0) * r.quantity for r in cheaper), 2
            ),
            "preference_swaps": len(matched_swaps),
            "filtered_count": split["filtered_count"],
            "filtered_spend": split["filtered_spend"],
            "based_on_weeks": round(weeks, 1),
            "receipts": len(orders),
        },
    }
