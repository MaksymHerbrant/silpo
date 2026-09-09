"""Збірка кошика на тиждень під ціль гостя.

Це головна дія застосунку. Логіка навмисно детермінована: LLM тут не потрібен,
бо задача — жадібний вибір товарів під обмеження (норми, бюджет, алергени),
а не творчість. Агент поверх цього вміє те, чого не вміє жадібний алгоритм:
розуміти вільний запит («без риби», «щоб було що брати на роботу»).

Принципи, які роблять результат прийнятним для людини:
  1. Беремо СПЕРШУ те, що гість уже купує — знайомі товари, а не «корисні».
  2. Дефіцити закриваємо пошуком у каталозі, але з тієї самої ролі.
  3. Ніколи не пропонуємо те, що конфліктує з обмеженнями профілю.
  4. Тримаємось бюджету: якщо не влазимо — ріжемо надлишкові категорії.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.mcp import tools as T
from app.nutrition import allergens as al
from app.nutrition.parser import ProductInfo, parse_product
from app.nutrition.targets import Targets

# Роль товару в раціоні — за нею добираємо заміни й закриваємо дефіцити
ROLE_MARKERS: dict[str, tuple[str, ...]] = {
    "protein": ("філе", "куряч", "індич", "яловичин", "свинин", "фарш", "риба", "лосос",
                "тунец", "яйц", "сир", "творог", "кефір", "йогурт", "квасол", "нут", "сочевиц"),
    "carbs": ("хліб", "багет", "крупа", "рис", "гречк", "макарон", "паста", "борошн",
              "пластівц", "мюслі", "картопл", "булг", "кус-кус", "лаваш"),
    "veg": ("огірок", "помідор", "капуст", "морква", "цибул", "перець", "кабач", "броколі",
            "салат", "зелень", "шпинат", "гриб", "буряк", "гарбуз"),
    "fruit": ("яблук", "банан", "груш", "апельсин", "мандарин", "ягод", "виноград",
              "ківі", "лимон", "авокадо", "слив", "персик"),
    "fat": ("олія", "масло", "горіх", "мигдал", "насіння", "авокадо", "паста арахіс"),
    "snack": ("чіпс", "снек", "печив", "шоколад", "цукерк", "батончик", "вафл", "сухарик",
              "попкорн", "крекер", "хлібц"),
    "drink": ("вода", "напій", "сік", "чай", "кава", "кола", "лимонад", "пиво", "вино"),
}

# Що шукати в каталозі, коли бракує нутрієнта. Порядок = пріоритет.
GAP_QUERIES: dict[str, list[str]] = {
    "protein": ["Філе куряче охолоджене", "Яйця курячі С0", "Сир кисломолочний 5%",
                "Йогурт грецький без цукру", "Тунець консервований у власному соку",
                "Індичка філе", "Сир твердий"],
    "carbs": ["Крупа гречана", "Рис довгозернистий", "Вівсяні пластівці",
              "Хліб цільнозерновий", "Макарони з твердих сортів"],
    "fat": ["Олія оливкова", "Горіхи волоські", "Мигдаль", "Авокадо"],
    "veg": ["Броколі заморожені", "Огірки", "Помідори", "Морква", "Капуста цвітна заморожена"],
    "fruit": ["Банани", "Яблука", "Мандарини"],
}

MAX_HABIT_PRODUCTS = 25
MAX_QTY_PER_ITEM = 4

# Ролі, з яких взагалі можна будувати раціон. Соуси, снеки, напої й алкоголь
# сюди не входять: жадібний алгоритм інакше набиває кошик майонезом, бо це
# найдешевші калорії на гривню — формально правильно, по суті безглуздо.
FOOD_ROLES = {"protein", "carbs", "veg", "fruit", "fat"}
EXCLUDE_MARKERS = (
    # приправи й соуси — найдешевші калорії на гривню, але не їжа
    "майонез", "кетчуп", "соус", "приправ", "спеці", "оцет", "маргарин",
    "сироп", "цукор", "сіль ", "розпушувач", "желатин",
    # не їжа
    "пакет", "серветк", "мило", "паста зубна", "корм", "тютюн",
    # готові страви й дитяче харчування: дорого за грам і не «база раціону»
    "готов", "печена", "запечена", "салат олів", "суші", "піца", "бургер готов",
    "пюре «чудо", "чудо-чадо", "дитяч", "з 6 місяців", "з 4 місяців",
)
MIN_ITEM_SCORE = 45          # товар із гіршою оцінкою в план не потрапляє
MAX_PRICE_PER_1000KCAL = 220.0   # дорожче — це делікатес, а не основа раціону

# Базові продукти: дешеві, ситні, з них будується основа тижня
STAPLE_QUERIES = {
    "carbs": ["Крупа гречана", "Рис круглозернистий", "Вівсяні пластівці",
              "Макарони з твердих сортів", "Картопля", "Хліб цільнозерновий"],
    "protein": ["Філе куряче охолоджене", "Яйця курячі С1", "Сир кисломолочний 9%",
                "Стегно куряче", "Печінка куряча", "Квасоля консервована"],
    "fat": ["Олія соняшникова", "Олія оливкова", "Масло вершкове 82%"],
}


def is_food(product: ProductInfo) -> bool:
    """Чи можна взагалі будувати з цього раціон."""
    low = f"{product.title} {product.brand or ''}".lower()
    if any(m in low for m in EXCLUDE_MARKERS):
        return False
    if product.is_alcohol:
        return False
    if product.is_liquid and (product.nutrition.carbs or 0) >= 4:
        return False           # солодкі напої
    if not product.weight_g:
        # Без ваги упаковки будь-який розрахунок покриття — вигадка.
        # Краще не брати товар, ніж підставляти 300 г навмання.
        return False
    if price_per_1000kcal(product) > MAX_PRICE_PER_1000KCAL:
        return False           # креветки за 299 ₴ — не база тижневого раціону
    return classify_role(product) in FOOD_ROLES


def price_per_1000kcal(product: ProductInfo) -> float:
    """Скільки коштує 1000 ккал із цього товару. Головний фільтр здорового глузду."""
    kcal = (product.nutrition.energy_kcal or 0) * (product.weight_g or 0) / 100
    if kcal <= 0:
        return float("inf")
    return (product.price or 0) / kcal * 1000


def classify_role(product: ProductInfo) -> str:
    low = f"{product.title} {product.brand or ''}".lower()
    for role, markers in ROLE_MARKERS.items():
        if any(m in low for m in markers):
            return role
    n = product.nutrition
    if n.protein and n.protein >= 12:
        return "protein"
    if n.carbs and n.carbs >= 40:
        return "carbs"
    return "other"


@dataclass
class PlanItem:
    slug: str
    product_id: str
    title: str
    role: str
    quantity: int
    unit_grams: float
    price: float
    old_price: float
    saved: float
    on_promotion: bool
    image: str | None
    kcal: float
    protein: float
    fat: float
    carbs: float
    familiar: bool          # чи купує гість це регулярно
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug, "product_id": self.product_id, "title": self.title,
            "role": self.role, "quantity": self.quantity, "price": round(self.price, 2),
            "old_price": round(self.old_price, 2), "saved": round(self.saved, 2),
            "on_promotion": self.on_promotion,
            "image": self.image, "familiar": self.familiar, "reason": self.reason,
            "kcal": round(self.kcal), "protein": round(self.protein, 1),
            "fat": round(self.fat, 1), "carbs": round(self.carbs, 1),
        }


def _contribution(product: ProductInfo, grams: float) -> dict[str, float]:
    n = product.nutrition
    k = grams / 100
    return {
        "kcal": (n.energy_kcal or 0) * k,
        "protein": (n.protein or 0) * k,
        "fat": (n.fat or 0) * k,
        "carbs": (n.carbs or 0) * k,
    }


def _grams_of(product: ProductInfo) -> float:
    """Вага упаковки. Товари без ваги у план не потрапляють (див. is_food)."""
    return product.weight_g or 300.0   # фолбек лише для аналітики, не для плану


PROMO_BOOST = 1.25   # акційний товар за інших рівних виграє


def _value_per_uah(product: ProductInfo, need: dict[str, float]) -> float:
    """Скільки дефіциту закриває одна упаковка на кожну витрачену гривню.

    Акційні товари отримують надбавку: за інших рівних гість має купити те,
    що зараз дешевше — це і його економія, і оборот акційної позиції для Сільпо.
    """
    price = product.price or 0
    if price <= 0:
        return 0.0
    contribution = _contribution(product, _grams_of(product))
    covered = 0.0
    for nutrient in ("protein", "kcal", "fat", "carbs"):
        deficit = max(need.get(nutrient, 0), 0)
        if deficit <= 0:
            continue
        # нормуємо, щоб білок і калорії були порівнянні між собою
        weight = 4.0 if nutrient == "protein" else 1.0
        covered += min(contribution[nutrient], deficit) / deficit * weight
    value = covered / price * 100
    return value * PROMO_BOOST if product.on_promotion else value



@dataclass
class WeeklyPlan:
    items: list[PlanItem] = field(default_factory=list)
    budget: float | None = None
    total_price: float = 0.0
    total_saved: float = 0.0
    total_old_price: float = 0.0
    need: dict[str, float] = field(default_factory=dict)
    covered: dict[str, float] = field(default_factory=dict)
    targets_week: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        coverage_pct = {
            k: int(round(self.covered.get(k, 0) / v * 100)) if v else 0
            for k, v in self.targets_week.items()
        }
        return {
            "items": [i.as_dict() for i in self.items],
            "budget": self.budget,
            "total_price": round(self.total_price, 2),
            "total_saved": round(self.total_saved, 2),
            "total_old_price": round(self.total_old_price, 2),
            "promo_items": sum(1 for i in self.items if i.on_promotion),
            "targets_week": {k: round(v) for k, v in self.targets_week.items()},
            "covered": {k: round(v) for k, v in self.covered.items()},
            "coverage_pct": coverage_pct,
            "familiar_share": (
                int(round(sum(1 for i in self.items if i.familiar) / len(self.items) * 100))
                if self.items else 0
            ),
            "notes": self.notes,
        }


async def _load_habit_products(api, ctx: T.CartContext, orders) -> dict[str, tuple[ProductInfo, int]]:
    """Товари, які гість купує регулярно, з їхньою частотою."""
    frequency: dict[str, int] = {}
    for order in orders:
        for line in order.items:
            slug = line.get("slug")
            if slug:
                frequency[slug] = frequency.get(slug, 0) + 1

    out: dict[str, tuple[ProductInfo, int]] = {}
    for slug, times in sorted(frequency.items(), key=lambda x: -x[1])[:MAX_HABIT_PRODUCTS]:
        try:
            payload = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(slug))
        except Exception:  # noqa: BLE001
            continue
        if T.is_mcp_error(payload):
            continue
        product = parse_product(payload, fallback_slug=slug)
        if product.has_nutrition:
            out[slug] = (product, times)
    return out


async def _search_products(api, ctx: T.CartContext, queries: list[str]) -> list[ProductInfo]:
    payload = await api.call(T.FIND_PRODUCTS_BATCH, ctx.as_args(products=queries[:30]))
    if T.is_mcp_error(payload) or not isinstance(payload, dict):
        return []
    found: list[ProductInfo] = []
    seen: set[str] = set()
    for block in payload.get("queries") or []:
        for raw in (block.get("products") or [])[:4]:
            slug = raw.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            try:
                detail = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(slug))
            except Exception:  # noqa: BLE001
                continue
            if T.is_mcp_error(detail):
                continue
            product = parse_product(detail, fallback_slug=slug, fallback_title=raw.get("name") or "")
            product.product_id = product.product_id or str(raw.get("id") or "")
            if product.has_nutrition:
                found.append(product)
    return found


def _blocked(product: ProductInfo, restrictions: list[al.Restriction]) -> bool:
    return bool(al.check_product(product, restrictions))


async def build_weekly_plan(
    api,
    ctx: T.CartContext,
    targets: Targets,
    orders,
    restrictions: list[al.Restriction],
    budget: float | None = None,
    household: int = 1,
    preferences: str | None = None,
    prefer_promo: bool = True,
) -> WeeklyPlan:
    days = 7
    targets_week = {
        "kcal": targets.kcal * days * household,
        "protein": targets.protein * days * household,
        "fat": targets.fat * days * household,
        "carbs": targets.carbs * days * household,
    }
    need = dict(targets_week)
    plan = WeeklyPlan(budget=budget, targets_week=targets_week, need=dict(need))

    from app.nutrition.score import score_product

    def eligible(product: ProductInfo) -> bool:
        if not is_food(product):
            return False
        if _blocked(product, restrictions):
            return False
        scored = score_product(product)
        return scored.score is None or scored.score >= MIN_ITEM_SCORE

    def spend(product: ProductInfo, familiar: bool, reason: str) -> bool:
        """Кладе одну упаковку в план, якщо вона влазить у бюджет."""
        price = product.price or 0
        if budget is not None and plan.total_price + price > budget:
            return False
        grams = _grams_of(product)
        contribution = _contribution(product, grams)
        saved = product.discount

        existing = next((i for i in plan.items if i.slug == product.slug), None)
        if existing:
            if existing.quantity >= MAX_QTY_PER_ITEM:
                return False
            existing.quantity += 1
            existing.price += price
            existing.old_price += (product.old_price or price)
            existing.saved += saved
            existing.kcal += contribution["kcal"]
            existing.protein += contribution["protein"]
            existing.fat += contribution["fat"]
            existing.carbs += contribution["carbs"]
        else:
            plan.items.append(PlanItem(
                slug=product.slug, product_id=product.product_id, title=product.title,
                role=classify_role(product), quantity=1, unit_grams=grams, price=price,
                old_price=(product.old_price or price), saved=saved,
                on_promotion=product.on_promotion,
                image=product.image, kcal=contribution["kcal"],
                protein=contribution["protein"], fat=contribution["fat"],
                carbs=contribution["carbs"], familiar=familiar, reason=reason,
            ))
        plan.total_price += price
        plan.total_saved += saved
        plan.total_old_price += (product.old_price or price)
        for key, value in contribution.items():
            need[key] = need.get(key, 0) - value
            plan.covered[key] = plan.covered.get(key, 0) + value
        return True

    # --- Крок 0: AI пропонує структуру раціону під ціль і побажання гостя.
    # Модель дає лише НАЗВИ для пошуку — ціни, калорії й відбір рахує код нижче.
    # Якщо LLM недоступний, працюють статичні STAPLE_QUERIES.
    from app.llm import advisor

    habit_titles: list[str] = []
    for order in orders[:10]:
        for line in order.items:
            if line.get("name") and line["name"] not in habit_titles:
                habit_titles.append(line["name"])

    ai_structure = await advisor.week_structure(
        targets.as_dict(), habit_titles, [r.label for r in restrictions],
        budget, preferences, household,
    )
    ai_queries: dict[str, list[str]] = {}
    if ai_structure:
        plan.notes.append(ai_structure.get("strategy", "")[:200])
        for group in ai_structure["groups"]:
            ai_queries.setdefault(group["role"], []).extend(group["queries"])

    def queries_for(role: str) -> list[str]:
        """Спершу те, що запропонував AI, потім наш статичний список."""
        return (ai_queries.get(role) or []) + STAPLE_QUERIES.get(role, [])

    # --- Крок 1: база. Дешеві крупи, м'ясо, яйця — те, з чого будується тиждень.
    # Спершу саме база, бо інакше бюджет з'їдають дорогі знайомі товари,
    # і на вуглеводи з білком уже не лишається.
    staple_budget = (budget * 0.6) if budget else None
    for nutrient in ("protein", "carbs"):
        found = await _search_products(api, ctx, queries_for(nutrient))
        ranked = sorted(
            (p for p in found if eligible(p)), key=lambda p: -_value_per_uah(p, need)
        )
        for product in ranked[:3]:
            for _ in range(MAX_QTY_PER_ITEM):
                if need.get(nutrient, 0) <= targets_week[nutrient] * 0.35:
                    break
                if staple_budget and plan.total_price + (product.price or 0) > staple_budget:
                    break
                if not spend(product, False, "база раціону"):
                    break

    # --- Крок 2: знайомі товари. Раціон має бути з того, що гість реально їсть.
    habits = await _load_habit_products(api, ctx, orders)
    familiar_pool = [
        (product, times) for product, times in habits.values() if eligible(product)
    ]
    familiar_pool.sort(key=lambda x: -x[1])
    for product, times in familiar_pool:
        if need.get("kcal", 0) <= targets_week["kcal"] * 0.1:
            break
        spend(product, True, f"купуєте регулярно ({times} раз(и))")

    # --- Крок 3: овочі й фрукти. Не за нутрієнтами — за тим, що їх майже не купують.
    if not any(i.role in ("veg", "fruit") for i in plan.items):
        veg_queries = (queries_for("veg")[:3] or GAP_QUERIES["veg"][:3])
        fruit_queries = (queries_for("fruit")[:2] or GAP_QUERIES["fruit"][:2])
        found = await _search_products(api, ctx, veg_queries + fruit_queries)
        for product in [p for p in found if eligible(p)][:3]:
            spend(product, False, "овочів і фруктів у ваших чеках майже немає")

    # --- Крок 4: добиваємо те, чого все ще бракує
    for nutrient in ("protein", "carbs", "fat"):
        if need.get(nutrient, 0) <= targets_week[nutrient] * 0.2:
            continue
        found = await _search_products(api, ctx, queries_for(nutrient) or GAP_QUERIES.get(nutrient, []))
        ranked = sorted((p for p in found if eligible(p)), key=lambda p: -_value_per_uah(p, need))
        for product in ranked[:3]:
            for _ in range(MAX_QTY_PER_ITEM):
                if need.get(nutrient, 0) <= targets_week[nutrient] * 0.2:
                    break
                if not spend(product, False, f"закриває дефіцит: {nutrient}"):
                    break

    if plan.total_saved > 0:
        plan.notes.append(
            f"На акційних позиціях економите {plan.total_saved:.0f} ₴ "
            f"({sum(1 for i in plan.items if i.on_promotion)} товар(ів))"
        )
    if budget is not None and plan.total_price > budget * 0.98:
        plan.notes.append(f"Уклались у бюджет {budget:.0f} ₴ впритул")
    if restrictions:
        plan.notes.append(
            "Виключили все, що конфліктує з вашими обмеженнями: "
            + ", ".join(r.label for r in restrictions)
        )
    return plan
