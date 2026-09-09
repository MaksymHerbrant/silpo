"""Health Score — детермінований розрахунок, БЕЗ участі LLM.

ЧОМУ НЕ NUTRI-SCORE. Спершу була реалізована класична модель Nutri-Score, але
пробні виклики MCP показали: каталог Сільпо не віддає ані цукру, ані насичених
жирів, ані солі, ані клітковини — лише «Енергетична цінність», «Білки»,
«Жири», «Вуглеводи» (і ті приблизно в 60% товарів). Nutri-Score стоїть саме на
відсутніх полях, тож на реальних даних він давав би «н/д» для 100% кошика.

ЩО ВИКОРИСТОВУЄМО НАТОМІСТЬ. Дві публічні, перевірювані референсні шкали:

1. AMDR — Acceptable Macronutrient Distribution Ranges (ВООЗ/FAO 916 та EFSA
   Dietary Reference Values): частка енергії з білків 10–20%, з жирів 20–35%,
   з вуглеводів 45–60%. Кошик — це наближення раціону, тож ці діапазони
   застосовні саме до сукупного профілю покупок.
2. Енергетична щільність (ккал на 100 г) — індикатор, який ВООЗ і WCRF
   використовують у рекомендаціях щодо ваги: раціон із щільністю до ~125
   ккал/100 г вважається сприятливим, понад ~275 — несприятливим.

Оцінка = 100 мінус штрафи за вихід за ці межі. Жодних «ваг на око»: кожен
коефіцієнт прив'язаний до опублікованого діапазону, а формула лінійна й
пояснювана на екрані користувача.

ОБМЕЖЕННЯ (декларуємо явно): без даних про цукор, насичені жири й сіль
модель не відрізнить солодкий газований напій від соку — обидва дадуть
однаковий макропрофіль. Тому окремо показуємо попередження за складом
(«Містить алергени», «Склад») і не називаємо це медичною рекомендацією.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.nutrition.parser import Nutrition, ProductInfo

KCAL_PER_G = {"protein": 4.0, "fat": 9.0, "carbs": 4.0}

# AMDR, частка енергії (%)
AMDR = {"protein": (10.0, 20.0), "fat": (20.0, 35.0), "carbs": (45.0, 60.0)}

# Енергетична щільність кошика, ккал/100 г
ED_GOOD, ED_BAD = 125.0, 275.0

# Скільки балів коштує 1 процентний пункт виходу за AMDR
PP_PENALTY = {"protein": 1.2, "fat": 1.4, "carbs": 0.8}
MAX_MACRO_PENALTY = 45.0   # сумарна стеля штрафу за макробаланс
MAX_ED_PENALTY = 30.0      # стеля штрафу за енергетичну щільність

DEFAULT_GRAMS = 300.0      # якщо вага товару невідома — консервативна оцінка

# --- Оцінка ОКРЕМОГО товару ------------------------------------------------
# AMDR описує раціон, а не окремий продукт (за ним куряче філе й кола виходять
# однаково «розбалансованими»), тому товар оцінюємо іншою, теж прозорою шкалою:
#   * вуглеводна щільність — проксі до цукру, якого каталог не віддає;
#     для напоїв шкала жорсткіша (ВООЗ радить уникати калорійних напоїв узагалі);
#   * енергетична щільність;
#   * бонус за білок;
#   * штраф за алкоголь.
CARB_REF_SOLID = 50.0      # г вуглеводів на 100 г = максимальний штраф
CARB_REF_LIQUID = 5.0      # г на 100 мл — «солодкий напій» починається приблизно тут
CARB_MAX_PENALTY = 40.0
ED_ITEM_MAX_PENALTY = 30.0
PROTEIN_REF = 12.0         # г білка на 100 г для повного бонусу
PROTEIN_MAX_BONUS = 20.0
ALCOHOL_PENALTY = 20.0


def energy_shares(protein: float, fat: float, carbs: float) -> dict[str, float]:
    """Частки енергії з макронутрієнтів, %."""
    total = protein * KCAL_PER_G["protein"] + fat * KCAL_PER_G["fat"] + carbs * KCAL_PER_G["carbs"]
    if total <= 0:
        return {"protein": 0.0, "fat": 0.0, "carbs": 0.0}
    return {
        "protein": round(protein * KCAL_PER_G["protein"] / total * 100, 1),
        "fat": round(fat * KCAL_PER_G["fat"] / total * 100, 1),
        "carbs": round(carbs * KCAL_PER_G["carbs"] / total * 100, 1),
    }


def amdr_deviation(shares: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Відхилення від AMDR у процентних пунктах (0 = в межах норми)."""
    deviations: dict[str, float] = {}
    for macro, (low, high) in AMDR.items():
        value = shares.get(macro, 0.0)
        deviations[macro] = round(low - value if value < low else (value - high if value > high else 0.0), 1)
    penalty = min(sum(deviations[m] * PP_PENALTY[m] for m in AMDR), MAX_MACRO_PENALTY)
    return penalty, deviations


def energy_density_penalty(kcal_per_100g: float | None) -> float:
    if kcal_per_100g is None:
        return 0.0
    if kcal_per_100g <= ED_GOOD:
        return 0.0
    ratio = (kcal_per_100g - ED_GOOD) / (ED_BAD - ED_GOOD)
    return round(min(ratio, 1.0) * MAX_ED_PENALTY, 1)


def to_letter(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "E"


@dataclass
class ScoredItem:
    product_id: str
    slug: str
    title: str
    brand: str | None
    image: str | None
    quantity: float
    grams: float | None
    price: float | None
    is_own_brand: bool
    is_alcohol: bool
    has_nutrition: bool
    nutrition: Nutrition | None
    score: int | None
    letter: str | None
    shares: dict[str, float] = field(default_factory=dict)
    kcal_total: float | None = None
    note: str | None = None
    allergens_text: str | None = None
    ingredients: str | None = None


@dataclass
class BasketScore:
    score: int
    letter: str
    shares: dict[str, float]
    deviations: dict[str, float]
    energy_density: float | None
    penalties: dict[str, float]
    totals: dict[str, float]
    covered_items: int
    skipped_items: int
    coverage_pct: int
    methodology: str = (
        "Оцінка рахується детерміновано: частка енергії з білків, жирів і вуглеводів "
        "звіряється з діапазонами AMDR (ВООЗ/EFSA: 10–20% / 20–35% / 45–60%), плюс "
        "штраф за енергетичну щільність кошика. Каталог Сільпо не містить даних про "
        "цукор, насичені жири й сіль, тому вони не враховані. Це не медична рекомендація."
    )


def item_grams(product: ProductInfo, quantity: float, weighted: bool = False) -> float:
    if weighted:
        # вагові товари: кількість — це кілограми
        return max(quantity, 0.01) * 1000
    grams = product.weight_g or DEFAULT_GRAMS
    return grams * max(quantity, 1)


def score_product(product: ProductInfo, quantity: float = 1.0, weighted: bool = False) -> ScoredItem:
    grams = item_grams(product, quantity, weighted)
    base = dict(
        product_id=product.product_id, slug=product.slug, title=product.title,
        brand=product.brand, image=product.image, quantity=quantity, grams=round(grams, 1),
        price=product.price, is_own_brand=product.is_own_brand, is_alcohol=product.is_alcohol,
        allergens_text=product.allergens_text, ingredients=product.ingredients,
    )
    n = product.nutrition
    if not product.has_nutrition:
        return ScoredItem(
            **base, has_nutrition=False, nutrition=None, score=None, letter=None,
            note="Немає даних про харчову цінність — товар не враховано в оцінці",
        )

    shares = energy_shares(n.protein or 0, n.fat or 0, n.carbs or 0)
    carb_ref = CARB_REF_LIQUID if product.is_liquid else CARB_REF_SOLID
    carb_penalty = min((n.carbs or 0) / carb_ref, 1.0) * CARB_MAX_PENALTY
    ed_penalty = 0.0
    if n.energy_kcal is not None and n.energy_kcal > ED_GOOD:
        ed_penalty = min((n.energy_kcal - ED_GOOD) / (400 - ED_GOOD), 1.0) * ED_ITEM_MAX_PENALTY
    protein_bonus = min((n.protein or 0) / PROTEIN_REF, 1.0) * PROTEIN_MAX_BONUS
    alcohol_penalty = ALCOHOL_PENALTY if product.is_alcohol else 0.0

    raw = 100 - carb_penalty - ed_penalty - alcohol_penalty + protein_bonus
    score = int(round(max(0.0, min(100.0, raw))))

    notes = []
    if product.is_alcohol:
        notes.append("алкоголь")
    if product.is_liquid and (n.carbs or 0) >= 5:
        notes.append(f"солодкий напій: {n.carbs} г вуглеводів на 100 мл")
    return ScoredItem(
        **base, has_nutrition=True, nutrition=n, score=score, letter=to_letter(score),
        shares=shares, kcal_total=round((n.energy_kcal or 0) * grams / 100, 1),
        note=", ".join(notes) or None,
    )


def score_basket(items: Iterable[ScoredItem]) -> BasketScore:
    items = list(items)
    scored = [i for i in items if i.has_nutrition and i.nutrition]
    skipped = len(items) - len(scored)

    if not scored:
        return BasketScore(
            score=0, letter="—", shares={}, deviations={}, energy_density=None,
            penalties={}, totals={}, covered_items=0, skipped_items=skipped, coverage_pct=0,
        )

    def total_grams_of(attr: str) -> float:
        return sum(
            (getattr(i.nutrition, attr) or 0) * (i.grams or DEFAULT_GRAMS) / 100 for i in scored
        )

    protein_g, fat_g, carbs_g = (total_grams_of(a) for a in ("protein", "fat", "carbs"))
    kcal = sum((i.nutrition.energy_kcal or 0) * (i.grams or DEFAULT_GRAMS) / 100 for i in scored)
    mass = sum(i.grams or DEFAULT_GRAMS for i in scored)

    shares = energy_shares(protein_g, fat_g, carbs_g)
    macro_penalty, deviations = amdr_deviation(shares)
    density = round(kcal / mass * 100, 1) if mass else None
    ed_penalty = energy_density_penalty(density)
    score = int(round(max(0.0, min(100.0, 100 - macro_penalty - ed_penalty))))

    return BasketScore(
        score=score,
        letter=to_letter(score),
        shares=shares,
        deviations=deviations,
        energy_density=density,
        penalties={"macro_balance": round(macro_penalty, 1), "energy_density": ed_penalty},
        totals={
            "calories": round(kcal),
            "protein": round(protein_g, 1),
            "fat": round(fat_g, 1),
            "carbs": round(carbs_g, 1),
            "mass_g": round(mass),
            "price": round(sum(i.price or 0 for i in items), 2),
        },
        covered_items=len(scored),
        skipped_items=skipped,
        coverage_pct=int(round(len(scored) / max(len(items), 1) * 100)),
    )
