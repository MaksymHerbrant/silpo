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

import asyncio

from dataclasses import dataclass, field
from typing import Any

from app.mcp import tools as T
from app.nutrition import allergens as al
from app.nutrition import categories as cats
from app.nutrition.parser import ProductInfo, parse_product
from app.nutrition.rules import match_rule
from app.nutrition.score import score_product
from app.services import kinds
from app.services import noise as noise_filter
from app.services import pricing
from app.services import profile as profile_service

# Дії, які гість може прийняти щодо позиції свого звичного набору
ACTION_KEEP = "keep"        # лишити як є
ACTION_SWITCH = "switch"    # замінити на знайдену альтернативу
ACTION_ADD = "add"          # докупити (акція на те, що зазвичай береш)
ACTION_REVIEW = "review"    # варте уваги: подорожчало або є вигідніший аналог
ACTION_BLOCKED = "blocked"  # конфліктує з обмеженнями гостя — не пропонуємо

MAX_ALTERNATIVE_LOOKUPS = 3
MAX_CANDIDATES = 2
# Загальна стеля на пошуки альтернатив за одну побудову. Кожен пошук — це
# виклик find_products_batch плюс до трьох get_product_details, тобто
# найдорожча частина. Без стелі побудова тягнеться понад хвилину і встигає
# застати обрив зʼєднання.
# Виклики тепер ідуть паралельно, тож стеля може бути вищою
MAX_TOTAL_SEARCHES = 8
MIN_SAVING = 5.0            # менша різниця в ціні не варта уваги гостя
# Наскільки дорожчою може бути альтернатива — вирішує НЕ цей файл, а гість.
# Поріг живе в services/pricing.py і приходить сюди параметром `tolerance`.

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
    # Вид товару й лояльність до марки всередині нього
    kind_key: str | None = None
    kind_brands: int = 1
    loyalty: float | None = None
    brand_indifferent: bool = False
    kind_note: str = ""
    members: list[dict[str, Any]] = field(default_factory=list)
    habit: dict[str, Any] | None = None   # розподіл покупок у часі
    cadence: str = "weekly"         # weekly | biweekly | monthly
    cadence_label: str = ""
    cycle_days: int = 7
    allergen_hits: list[dict[str, Any]] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    saved: float = 0.0
    on_promotion: bool = False
    old_price: float | None = None
    alternative: dict[str, Any] | None = None
    # Варіанти, які знайшлися, але вийшли за ціновий поріг гостя. Ми їх не
    # підставляємо — вони доступні лише через «показати ще варіанти».
    alternatives_over: list[dict[str, Any]] = field(default_factory=list)
    selected: bool = True          # у плані за замовчуванням, гість може зняти

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug, "product_id": self.product_id, "name": self.name,
            "image": self.image, "price": self.price, "quantity": self.quantity,
            "category": self.category, "category_label": cats.CATEGORY_LABELS.get(self.category, ""),
            "times_bought": self.times_bought, "action": self.action, "note": self.note,
            "saved": round(self.saved, 2), "on_promotion": self.on_promotion,
            "old_price": self.old_price, "alternative": self.alternative,
            "alternatives_over": self.alternatives_over,
            "selected": self.selected,
            "line_total": round(self.price * self.quantity, 2),
            "kind": self.kind, "kind_reason": self.kind_reason, "habit": self.habit,
            "kind_key": self.kind_key, "kind_brands": self.kind_brands,
            "loyalty": self.loyalty, "brand_indifferent": self.brand_indifferent,
            "kind_note": self.kind_note, "members": self.members,
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


@dataclass
class Alternatives:
    """Кандидати, розділені ціновим порогом гостя.

    `within` — те, що показуємо за замовчуванням. `over` — те, що існує, але
    виходить за поріг: воно живе під «показати ще варіанти» і ніколи не
    підставляється саме собою.
    """
    within: list[tuple[ProductInfo, float]] = field(default_factory=list)
    over: list[tuple[ProductInfo, float]] = field(default_factory=list)


def _health_of(product: ProductInfo) -> int:
    """Детермінований бал товару 0–100. Вирішує лише всередині цінової смуги."""
    try:
        return score_product(product).score or 0
    except Exception:  # noqa: BLE001 — скор не має валити пошук замін
        return 0


def _composition_known(product: ProductInfo) -> bool:
    """Чи є в каталозі хоч якісь дані про склад цього товару.

    Критично для обіцянки безпеки: ВІДСУТНІСТЬ даних про склад — не доказ
    відсутності алергену. Перевірено наживо: каталог віддав заміну без складу
    взагалі, і перевірка алергенів не мала що читати. Казати про такий товар
    «без вашого алергену» — це видавати незнання за гарантію.
    """
    return bool(product.allergens_text or product.ingredients)


def _alt_dict(
    candidate: ProductInfo, saving: float, why: str, over_threshold: bool = False
) -> dict[str, Any]:
    return {
        "slug": candidate.slug, "product_id": candidate.product_id,
        "name": candidate.title, "price": candidate.price, "image": candidate.image,
        "saved": saving, "on_promotion": candidate.on_promotion, "why": why,
        "over_threshold": over_threshold,
        "composition_known": _composition_known(candidate),
    }


# Службові слова, які лише подовжують запит і нічого не додають до пошуку
QUERY_STOP_WORDS = frozenset({
    "зі", "з", "із", "для", "та", "і", "й", "без", "у", "в", "на", "по",
    "смаком", "смак", "ароматом", "штук", "шт",
})


def _search_queries(product: ProductInfo) -> list[str]:
    """Короткі запити для пошуку аналогів.

    Каталог Сільпо не знаходить нічого за повною назвою товару. Перевірено
    наживо: «Снек пікантний Pringles зі смаком барбекю» дає 0 результатів,
    «Pringles» — 1, «чіпси» — 14. Тому назву треба вкоротити до того, що
    справді шукається: марка й головний іменник.
    """
    queries: list[str] = []
    if product.brand:
        queries.append(product.brand.strip())

    words = [w.strip("«»\"'`.,()–—") for w in product.title.split()]
    words = [w for w in words if w and w.lower() not in QUERY_STOP_WORDS]
    if words:
        queries.append(words[0])                      # «Молоко», «Снек», «Напій»
        if len(words) > 1:
            queries.append(" ".join(words[:2]))       # «Молоко Премія»

    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        key = query.lower()
        if len(query) >= 3 and key not in seen:
            seen.add(key)
            out.append(query)
    return out[:3] or [product.title]


def _first_safe(
    pairs: list[tuple[ProductInfo, float]], restrictions
) -> tuple[ProductInfo, float, bool] | None:
    """Перший кандидат без конфлікту. Спершу ті, чий склад ВІДОМИЙ.

    Це єдине місце, де безпека свідомо переважає ціну: коли позиція
    заблокована алергеном, товар із перевіреним складом кращий за трохи
    дешевший товар, про який ми нічого не знаємо.

    Третій елемент — чи склад справді перевірено. Він визначає формулювання
    в інтерфейсі, щоб незнання не виглядало гарантією.
    """
    unknown: tuple[ProductInfo, float, bool] | None = None
    for candidate, saving in pairs:
        if al.blocking(al.check_product(candidate, restrictions)):
            continue
        if _composition_known(candidate):
            return candidate, saving, True
        if unknown is None:
            unknown = (candidate, saving, False)
    return unknown


async def _find_alternatives(
    api, ctx: T.CartContext, product: ProductInfo, queries: list[str],
    tolerance: Any = pricing.DEFAULT_TOLERANCE,
) -> Alternatives:
    """Шукає аналоги тієї самої ролі й ділить їх ціновим порогом гостя.

    Порядок навмисний: спершу відсікаємо все, що виходить за поріг (ціна —
    критерій №1 за опитуванням), і лише всередині коридору сортуємо за
    користю. Так дієтологія ніколи не переважає гроші, але й не зникає.
    """
    payload = await api.call(T.FIND_PRODUCTS_BATCH, ctx.as_args(products=queries[:12]))
    if T.is_mcp_error(payload) or not isinstance(payload, dict):
        return Alternatives()

    # Мережева стеля: навіть «без обмежень» не тягне картки втричі дорожчих товарів
    hard_cap = pricing.cap_for(product.price, None)

    found: list[tuple[ProductInfo, float]] = []
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
            if hard_cap is not None and price > hard_cap:
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
            found.append((candidate, round(product.price - candidate.price, 2)))

    within, over = pricing.split(product.price, found, tolerance)
    return Alternatives(
        within=pricing.rank(within, _health_of),
        over=pricing.rank(over, _health_of),
    )


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


def habit_showcase(split: dict[str, Any]) -> dict[str, Any] | None:
    """Найнаочніша пара прикладів: сильна звичка проти слабкого сигналу.

    Це головний доказ того, що ми не рахуємо рядки чеків. Слабкий приклад —
    товар, який зʼявлявся багато разів, але майже все в один похід. Сильний —
    товар, куплений у багато різних днів, часто різних марок.

    Беремо з РЕАЛЬНИХ даних гостя, нічого не вигадуючи. Якщо переконливої
    пари немає — повертаємо None і в інтерфейсі нічого не показуємо.
    """
    weak = None
    for row in split.get("noise") or []:
        lines, days = int(row.get("lines") or 0), len(row.get("days") or [])
        if days and lines >= days * 3 and lines >= 4:
            if weak is None or lines > weak["lines"]:
                weak = {"name": row.get("name"), "lines": lines, "days": days}

    strong = None
    best_score = 0.0
    for row in split.get("basket") or []:
        # Пакети й серветки — супутні витратні, а не звичка. Вони б виграли
        # за частотою й зіпсували найнаочніший приклад продукту.
        if row.get("kind") == "companion":
            continue
        days = len(row.get("days") or [])
        if days < 5:
            continue
        habit = row.get("habit") or {}
        brands = int(row.get("kind_brands") or 1)
        # Найпереконливіший приклад — той, де багато днів І багато марок:
        # саме він показує, що звичка живе на рівні виду, а не артикула.
        score = days * (1 + (brands - 1) * 0.5 if row.get("brand_indifferent") else 1)
        if score <= best_score:
            continue
        best_score = score
        strong = {
            "name": row.get("name"), "days": days,
            "weeks": habit.get("weeks") or 0,
            "brands": brands,
            "kind": row.get("kind_key"),
            "brand_indifferent": bool(row.get("brand_indifferent")),
        }

    if not strong:
        return None
    return {"strong": strong, "weak": weak}


def _aggregate(orders) -> list[dict[str, Any]]:
    """Зводить чеки до агрегатів по товарах.

    `times` — це кількість РІЗНИХ ДНІВ, коли товар купували, а не кількість
    рядків у чеках. Різниця принципова: у одному чеку той самий товар може
    стояти кількома рядками. На живих даних форель мала вісім рядків — усі
    восьмеро за 7 вересня. Рахуючи рядки, ми оголошували один похід у магазин
    вісьмома покупками й називали це звичкою.
    """
    rows: dict[str, dict[str, Any]] = {}
    for order in orders:
        day = order.created_at.date().isoformat()
        for line in order.items:
            slug = line.get("slug")
            name = (line.get("name") or "").strip()
            if not slug and not name:
                continue

            # Позиція без catalogProduct (товар знято з продажу або не
            # зматчився) раніше мовчки викидалась. Так ми втрачали реальні
            # покупки: в одному чеку тестувальника так зникли три товари з
            # шістнадцяти, серед них пластівці, які він бере постійно.
            # Такий товар не можна покласти в кошик, але він ОБОВʼЯЗКОВО
            # має рахуватись у звичках.
            key = slug or f"noslug:{name.lower()}"
            row = rows.setdefault(key, {
                "slug": slug, "name": line.get("name"), "times": 0, "total_qty": 0.0,
                "spend": 0.0, "image": line.get("image"), "history": [], "_days": set(),
                "lines": 0, "no_catalog": not slug,
            })
            qty = float(line.get("quantity") or 1)
            price = float(line.get("price") or 0)
            row["lines"] += 1
            row["_days"].add(day)
            row["total_qty"] += qty
            row["spend"] += price * qty
            row["history"].append({
                "date": day, "price": price, "quantity": qty, "branch": order.branch,
            })

    out: list[dict[str, Any]] = []
    for row in rows.values():
        days = row.pop("_days")
        if row.get("no_catalog") and not row.get("slug"):
            # Стабільний ключ, щоб інтерфейс не падав на None
            row["slug"] = f"noslug:{(row.get('name') or '').lower()[:60]}"
        row["times"] = len(days)          # походів у магазин, а не рядків
        row["days"] = sorted(days)
        out.append(row)
    return out


class SearchBudget:
    """Простий лічильник: скільки пошуків альтернатив ще можна дозволити."""

    def __init__(self, limit: int = MAX_TOTAL_SEARCHES) -> None:
        self.left = limit

    def take(self) -> bool:
        if self.left <= 0:
            return False
        self.left -= 1
        return True


class AlternativeSearch:
    """Один товар шукаємо один раз за побудову.

    Без кешу позиція, для якої заміни не знайшлось у гілці вподобань,
    з'їдає бюджет ще раз у гілці дешевших аналогів — і товари нижче
    в списку не перевіряються взагалі. Саме через це в живому прогоні
    заміна на тютюн за 164.94 ₴ (−15 ₴) не доходила до гостя.
    """

    def __init__(self, api, ctx: T.CartContext, tolerance: Any) -> None:
        self._api = api
        self._ctx = ctx
        self._tolerance = tolerance
        self._budget = SearchBudget()
        self._cache: dict[tuple[str, tuple[str, ...]], Alternatives] = {}

    async def get(self, product: ProductInfo, queries: list[str]) -> Alternatives | None:
        """None означає «бюджет вичерпано», а не «нічого не знайшлось»."""
        key = (product.slug, tuple(queries))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if not self._budget.take():
            return None
        result = await _find_alternatives(
            self._api, self._ctx, product, queries, self._tolerance
        )
        self._cache[key] = result
        return result


# Модель може ПІДНЯТИ товар до звички лише якщо покупок було принаймні
# стільки. Це арифметика, а не судження: одна покупка не стає ритмом від
# того, що модель так вирішила.
LLM_PROMOTE_MIN_DAYS = 2
MAX_BASKET_ITEMS = 14


def _merge_verdicts(split: dict[str, Any], verdicts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Вердикт моделі вирішує склад кошика — в межах арифметичних поручнів.

    Скрипт рахує дати й дає першу оцінку. Модель бачить ТІ САМІ дати по всіх
    кандидатах, включно з відсіяними, і може як підняти товар до звички, так
    і прибрати. Пониження приймаємо завжди; підняття — лише коли покупок
    справді було кілька.
    """
    if not verdicts:
        return split

    by_slug = {r["slug"]: r for r in split["basket"] + split["noise"] if r.get("slug")}
    basket, noise, emerging, fading = [], [], [], []
    promoted = demoted = 0

    for slug, row in by_slug.items():
        judged = verdicts.get(slug)
        was_basket = row in split["basket"]
        verdict = judged["verdict"] if judged else None
        days = len(row.get("days") or [])

        if judged and judged.get("why"):
            row = {**row, "agent_why": judged["why"]}

        if verdict == "habit" and days >= LLM_PROMOTE_MIN_DAYS:
            if not was_basket:
                promoted += 1
                row = {**row, "kind": "regular", "kind_reason": judged.get("why") or row["kind_reason"]}
            basket.append(row)
        elif verdict in {"new", "dropped", "occasional"}:
            if was_basket and row.get("kind") != "companion":
                demoted += 1
            (emerging if verdict == "new" else fading if verdict == "dropped" else noise).append(row)
        elif was_basket:
            basket.append(row)
        else:
            noise.append(row)

    basket.sort(key=lambda r: (r["kind"] != "regular", -(r.get("spend") or 0)))
    return {
        **split,
        "basket": basket[:MAX_BASKET_ITEMS],
        "noise": sorted(noise, key=lambda r: -(r.get("spend") or 0)),
        "emerging": sorted(emerging, key=lambda r: -(r.get("spend") or 0)),
        "fading": sorted(fading, key=lambda r: -(r.get("spend") or 0)),
        "filtered_count": len(noise),
        "filtered_spend": round(sum(r.get("spend") or 0 for r in noise), 2),
        "agent_promoted": promoted,
        "agent_demoted": demoted,
    }


async def build(
    api, ctx: T.CartContext, orders, goal: str | None = None,
    tolerance: Any = pricing.DEFAULT_TOLERANCE,
    classifier=None,
) -> dict[str, Any]:
    """Складає план наступної покупки: профіль, фільтр шуму, знахідки.

    `tolerance` — ціновий поріг гостя з налаштувань. Він фільтрує кожну
    альтернативу ще до того, як та потрапить у знахідки.
    """
    search = AlternativeSearch(api, ctx, tolerance)
    if not orders:
        return {"has_data": False, "reason": "Чеків Сільпо поки не знайшли"}

    guest = await profile_service.load(api)
    restrictions = guest.get("restriction_objects") or []

    period_days = (
        max((orders[0].created_at - orders[-1].created_at).days, 1) if len(orders) > 1 else 7
    )
    # Звичка живе на рівні ВИДУ товару, не марки: «беру сир щотижня» —
    # а моцарела чи сулугуні залежить від того, що трапилось на полиці.
    # Без цього одна сильна звичка розсипалась на два десятки слабких.
    rows = kinds.group(_aggregate(orders))
    split = noise_filter.split(rows, receipts=len(orders), period_days=period_days)

    # Тютюн і алкоголь лишаємо в аналітиці витрат, але прибираємо звідси:
    # радити марку стиків, прив'язану до чужого пристрою, безглуздо.
    # Модель бачить УСІХ кандидатів — і тих, кого скрипт відсіяв
    if classifier is not None:
        try:
            verdicts = await classifier(
                split["basket"] + split["noise"], period_days,
                orders[0].created_at.date().isoformat(),
            )
            split = _merge_verdicts(split, verdicts)
        except Exception:  # noqa: BLE001 — модель необовʼязкова
            pass

    skipped = [
        r for r in split["basket"]
        if cats.categorize(r.get("name") or "") in cats.NO_RECOMMENDATION
    ]
    split["basket"] = [r for r in split["basket"] if r not in skipped]

    if not split["basket"]:
        return {"has_data": False, "reason": "У чеках немає товарів, які повторюються"}

    weeks = max(
        ((orders[0].created_at - orders[-1].created_at).days or 7) / 7, 1
    )

    # --- деталі товарів набору: ціна зараз, склад, алергени ---
    plan: list[PlanItem] = []
    products: dict[str, ProductInfo] = {}
    # Картки товарів незалежні одна від одної — тягнемо їх разом.
    # Це найдорожча частина побудови: двадцять із гаком послідовних
    # викликів по 0.6 с перетворювались на чверть усього часу.
    wanted = split["basket"][:12]
    fetched = await asyncio.gather(
        *(api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(r["slug"])) for r in wanted),
        return_exceptions=True,
    )

    for row, payload in zip(wanted, fetched):
        if isinstance(payload, BaseException) or T.is_mcp_error(payload):
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
            habit=row.get("habit"),
            kind_key=row.get("kind_key"), kind_brands=row.get("kind_brands", 1),
            loyalty=row.get("loyalty"), brand_indifferent=bool(row.get("brand_indifferent")),
            kind_note=kinds.describe(row), members=row.get("members") or [],
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
            # Вага потрібна, щоб зводити БЖВ по масі, а не середнім по товарах.
            # Цукор і сіль каталог Сільпо майже ніколи не віддає — тоді None,
            # і в інтерфейсі буде чесне «даних немає», а не нуль.
            "weight_g": product.weight_g,
            "nutrition": {
                "kcal": product.nutrition.energy_kcal, "protein": product.nutrition.protein,
                "fat": product.nutrition.fat, "carbs": product.nutrition.carbs,
                "sugar": product.nutrition.sugar, "salt": product.nutrition.salt,
                "saturated_fat": product.nutrition.saturated_fat,
                "fiber": product.nutrition.fiber,
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
        alternatives = await search.get(product, _search_queries(product))
        if alternatives is None:
            continue
        # Алерген — не питання смаку. Якщо чистого варіанта в межах порогу немає,
        # чесніше показати дорожчий і прямо це позначити, ніж не показати нічого.
        safe = _first_safe(alternatives.within, restrictions)
        over_threshold = False
        if safe is None:
            safe = _first_safe(alternatives.over, restrictions)
            over_threshold = safe is not None
        if safe:
            candidate, saving, verified = safe
            row.alternative = _alt_dict(
                candidate, saving,
                "склад перевірено — вашого алергену немає" if verified
                else "склад не вказано в каталозі — перевірте на упаковці",
                over_threshold=over_threshold,
            )
    if blocked:
        found = sum(1 for b in blocked if b.alternative)
        unverified = sum(
            1 for b in blocked
            if b.alternative and not b.alternative.get("composition_known")
        )
        detail = "У складі є те, що ви вказали в профілі Сільпо як алерген"
        if unverified:
            detail += (
                f". Для {unverified} заміни каталог не вказує складу — "
                "перевірте його на упаковці"
            )
        findings.append(Finding(
            kind="safety",
            title=f"{len(blocked)} позиції з вашим алергеном",
            value=f"{found} заміни знайдено" if found else "перевірте склад",
            detail=detail,
            slugs=[b.slug for b in blocked],
        ))

    # --- 🎯 заміни за вподобанням із профілю (цукор у солодких напоях тощо) ---
    for row in preference_swaps:
        product = products.get(row.slug)
        if product is None or row.alternative:
            continue
        rule = match_rule(product)
        queries = rule.queries if rule else _search_queries(product)
        alternatives = await search.get(product, queries)
        if alternatives is None:
            continue
        clean = [p for p in alternatives.within if not al.check_product(p[0], restrictions)]
        if not clean:
            # Варіанти є, але дорожчі за поріг. Самі не підставляємо — ховаємо
            # під «показати ще варіанти», щоб рішення лишилось за гостем.
            row.alternatives_over = [
                _alt_dict(c, s_, "поза вашим ціновим порогом", over_threshold=True)
                for c, s_ in alternatives.over
                if not al.check_product(c, restrictions)
            ][:2]
            continue
        best, saving = clean[0]     # вже відсортовано: спершу ціна, потім користь
        row.action = ACTION_SWITCH
        row.alternative = _alt_dict(
            best, saving,
            f"відповідає вашому «{row.allergen_hits[0]['restriction'].lower()}»",
        )
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
        row.note = f"зараз в акції, на {round(row.saved)} ₴ дешевше"
    if promos:
        total = sum(p.saved * p.quantity for p in promos)
        findings.append(Finding(
            kind="promo",
            title=f"{len(promos)} ваші звичні товари в акції",
            value=f"{round(total)} ₴",
            detail="Те, що ви й так берете, зараз дешевше",
            slugs=[p.slug for p in promos],
        ))

    # --- 🔁 марка байдужа → пропонуємо ту, що зараз в акції ---
    # Якщо гість щоразу бере інший сир, «замінити моцарелу на сулугуні» —
    # не заміна, а просто інша марка того самого. І якщо вона дешевша чи
    # в акції, це найкорисніша порада, яку ми взагалі можемо дати.
    brand_swaps: list[PlanItem] = []
    for row in plan:
        if not row.brand_indifferent or row.alternative or row.action == ACTION_BLOCKED:
            continue
        product = products.get(row.slug)
        if product is None:
            continue
        alternatives = await search.get(product, [row.kind_key or product.title])
        if alternatives is None:
            break
        # Цінність тут — саме ЗНИЖКА на іншу марку, а не те, що вона дешевша
        # за звичну. Але й дорожчати не має: акційний сир за 449 ₴ замість
        # звичних 70 ₴ — це не порада, хоч знижка там і 280 ₴.
        safe = [
            p for p in alternatives.within
            if p[0].on_promotion and p[1] >= 0
            and not al.check_product(p[0], restrictions)
            and _same_product_kind(product, p[0])
        ]
        if not safe:
            continue
        # Найбільша знижка серед тих, що вкладаються в звичну ціну
        best, saving = max(safe, key=lambda p: p[0].discount)
        row.action = ACTION_SWITCH
        row.alternative = _alt_dict(
            best, saving,
            f"ви берете {row.kind_key} різних марок — ця зараз зі знижкою "
            f"{round(best.discount)} ₴",
        )
        brand_swaps.append(row)

    if brand_swaps:
        total = sum((r.alternative or {}).get("saved", 0) * r.quantity for r in brand_swaps)
        findings.append(Finding(
            kind="brand",
            title=f"{len(brand_swaps)} види, де марка вам не принципова",
            value=f"{round(total)} ₴" if total > 0 else "є акційні",
            detail=(
                "Ви берете їх різних марок, тож можна взяти ту, що зараз зі знижкою"
            ),
            slugs=[r.slug for r in brand_swaps],
        ))

    # --- 🥗 одна конкретна зміна на краще ---
    health = _health_candidate(
        [p.as_dict() for p in plan if p.action == ACTION_KEEP and not p.alternative], products
    )
    health_slug: str | None = None
    if health:
        _weight, product, rule, _item = health
        alternatives = await search.get(product, rule.queries)
        safe = (
            [p for p in alternatives.within if not al.check_product(p[0], restrictions)]
            if alternatives else []
        )
        if safe:
            best, saving = safe[0]
            row = next((p for p in plan if p.slug == product.slug), None)
            if row is not None:
                row.action = ACTION_SWITCH
                row.alternative = _alt_dict(best, saving, rule.reason)
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
        alternatives = await search.get(product, _search_queries(product))
        if alternatives is None:
            break
        checked += 1
        safe = [p for p in alternatives.within if not al.check_product(p[0], restrictions)]
        if not safe:
            continue
        best, saving = safe[0]
        if saving < MIN_SAVING:
            continue
        row.action = ACTION_REVIEW
        row.note = f"є аналог на {round(saving)} ₴ дешевше"
        # Пошук іде за маркою й головним іменником, тож це схожий товар тієї
        # самої ролі, а не буквально та сама позиція. Формулюємо чесно.
        row.alternative = _alt_dict(best, saving, "схожий товар, дешевше")
        cheaper.append(row)

    if cheaper:
        total = sum((r.alternative or {}).get("saved", 0) * r.quantity for r in cheaper)
        findings.append(Finding(
            kind="alternative",
            title=f"{len(cheaper)} вигідніші аналоги",
            value=f"{round(total)} ₴",
            detail="Та сама роль у кошику, але дешевше",
            slugs=[r.slug for r in cheaper],
        ))

    # --- 🌱 нове у кошику: ще не звичка, але вже не випадковість ---
    emerging = split.get("emerging") or []
    if emerging:
        findings.append(Finding(
            kind="emerging",
            title=f"{len(emerging)} нових товари у вашому кошику",
            value="нове",
            detail=(
                "Взяли кілька разів нещодавно. Повториться в різні тижні — "
                "стане частиною звичного набору"
            ),
            slugs=[r["slug"] for r in emerging[:6]],
        ))

    # --- 🕰️ звичка, яка обірвалась ---
    fading = split.get("fading") or []
    if fading:
        findings.append(Finding(
            kind="fading",
            title=f"{len(fading)} позиції випали зі звички",
            value="давно не брали",
            detail="Раніше брали регулярно, останнім часом ні. Якщо потрібно — поверніть у набір",
            slugs=[r["slug"] for r in fading[:6]],
        ))

    # --- 💸 що саме приховав ціновий поріг ---
    # Показуємо це явно: інакше налаштування лишається невидимим, а гість не
    # розуміє, чому варіантів мало.
    hidden = sum(len(p.alternatives_over) for p in plan)
    if hidden:
        findings.append(Finding(
            kind="threshold",
            title=f"{hidden} варіанти приховано ціновим порогом",
            value=pricing.describe(tolerance),
            detail=(
                "Дорожчі за вашу межу. Поріг можна змінити в налаштуваннях, "
                "самі варіанти — у картці товару"
            ),
            slugs=[p.slug for p in plan if p.alternatives_over],
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
        "emerging": [
            {"name": r["name"], "slug": r["slug"], "spend": round(r["spend"], 2),
             "reason": r["kind_reason"], "habit": r.get("habit")}
            for r in emerging[:6]
        ],
        "fading": [
            {"name": r["name"], "slug": r["slug"], "spend": round(r["spend"], 2),
             "reason": r["kind_reason"], "habit": r.get("habit")}
            for r in fading[:6]
        ],
        "habit_showcase": habit_showcase(split),
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
            "skipped_categories": len(skipped),
            "agent_promoted": split.get("agent_promoted", 0),
            "agent_demoted": split.get("agent_demoted", 0),
            "based_on_weeks": round(weeks, 1),
            "receipts": len(orders),
            "price_tolerance": pricing.normalize(tolerance),
            "price_tolerance_label": pricing.describe(tolerance),
            "hidden_by_threshold": hidden,
        },
    }
