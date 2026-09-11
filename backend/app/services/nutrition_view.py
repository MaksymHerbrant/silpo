"""Екран «Харчування»: один бал, одне речення, деталі — за розгорткою.

Опитування 21 респондента: 57% хочуть коротке пояснення, 43% — простий бал
1–10, і лише 10% деталізацію. БЖВ та особисті цілі цікавлять по 52%, цукор —
14%, сіль — 5%. Звідси три рівні глибини, а не одна панель приладів.

Бал рахується ДЕТЕРМІНОВАНО і лише з того, що ми справді знаємо: зі структури
витрат на їжу. Це свідомо не «Health Score» — ми не ставимо діагноз товарам,
каталог для цього не має даних. Ми кажемо, наскільки структура витрат близька
до орієнтирів Гарвардської тарілки, і прямо називаємо це евристикою.

Важливо: бал рахується по ЇЖІ, а не по всьому чеку. Тютюн, побутова хімія й
вода не мають орієнтирів на тарілці, і якби вони лишались у знаменнику,
кошик із дорогим непродуктовим товаром завжди виглядав би «незбалансованим».
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.nutrition import categories as cats

# Категорії, які формують «тарілку». Решта (вода, кава, тютюн, побутове,
# інше) у бал не входить — для них немає орієнтира.
PLATE_CATEGORIES: tuple[str, ...] = tuple(cats.TARGET_SHARES.keys())

# Дільник підібраний так, щоб ідеальна структура давала 10, а кошик майже
# цілком із оброблених продуктів — 1.
DEVIATION_DIVISOR = 17.0

# Нижче цього покриття даними денні числа не показуємо: вони були б
# заниженими в рази і вводили б в оману.
MIN_COVERAGE_FOR_DAILY = 0.6

# Що шукати в каталозі, щоб підтягнути категорію. Запити короткі й перевірені
# наживо: каталог Сільпо відповідає лише на односкладові підрядки.
CATEGORY_QUERIES: dict[str, list[str]] = {
    "veg_fruit": ["Яблука", "Банан", "Помідори", "Морква"],
    "protein": ["Філе куряче", "Яйця", "Тунець", "Квасоля"],
    "grains": ["Хліб", "Гречка", "Рис", "Макарони"],
    "dairy": ["Йогурт", "Кефір", "Сир кисломолочний"],
}

PERIODS: dict[str, int | None] = {"week": 7, "month": 30, "all": None}
PERIOD_LABELS = {"week": "тиждень", "month": "місяць", "all": "весь період"}


def plate_uah(structure: cats.BasketStructure) -> dict[str, float]:
    """Витрати в гривнях по категоріях тарілки."""
    return {c.key: c.spend for c in structure.categories if c.key in PLATE_CATEGORIES}


def shares_from_uah(plate: dict[str, float]) -> dict[str, float]:
    total = sum(plate.values())
    if total <= 0:
        return {}
    return {key: value / total * 100 for key, value in plate.items()}


def uah_to_reach_target(plate: dict[str, float], key: str) -> float:
    """Скільки ₴ додати в категорію, щоб її частка дійшла до нижнього орієнтира.

    Додані гроші збільшують і знаменник, тому це не проста різниця:
        (spend + S) / (total + S) = target      →      S = (target·total − spend) / (1 − target)
    """
    low = cats.TARGET_SHARES[key][0] / 100
    total = sum(plate.values())
    spend = plate.get(key, 0.0)
    if total <= 0 or low >= 1:
        return 0.0
    need = (low * total - spend) / (1 - low)
    return max(need, 0.0)


def recommendations(structure: cats.BasketStructure) -> list[dict[str, Any]]:
    """Що додати, щоб бал наступного разу був вищим.

    Рахунок детермінований: беремо категорії нижче орієнтира, рахуємо потрібну
    суму й перевіряємо, чи бал справді зросте. Якщо ні — не радимо.
    """
    plate = plate_uah(structure)
    if not plate:
        return []
    now = balance_score(shares_from_uah(plate))

    out: list[dict[str, Any]] = []
    for key in PLATE_CATEGORIES:
        if key not in CATEGORY_QUERIES:
            continue
        need = uah_to_reach_target(plate, key)
        if need < 1:
            continue
        after = balance_score(shares_from_uah({**plate, key: plate.get(key, 0.0) + need}))
        if after <= now:
            continue
        out.append({
            "key": key,
            "label": cats.CATEGORY_LABELS.get(key, key),
            "need_uah": round(need),
            "score_now": now,
            "score_after": after,
            "queries": CATEGORY_QUERIES[key],
        })
    out.sort(key=lambda r: (-(r["score_after"] - r["score_now"]), r["need_uah"]))
    return out[:2]


def plate_shares(structure: cats.BasketStructure) -> dict[str, float]:
    """Частки всередині тарілки: знаменник — лише категорії з орієнтирами."""
    plate = {c.key: c.spend for c in structure.categories if c.key in PLATE_CATEGORIES}
    total = sum(plate.values())
    if total <= 0:
        return {}
    return {key: value / total * 100 for key, value in plate.items()}


def deviations(shares: dict[str, float]) -> list[tuple[str, float, str]]:
    """Наскільки кожна категорія виходить за свій орієнтир. (ключ, пункти, бік)."""
    out: list[tuple[str, float, str]] = []
    for key, (low, high) in cats.TARGET_SHARES.items():
        share = shares.get(key, 0.0)
        if share > high:
            out.append((key, share - high, "above"))
        elif share < low:
            out.append((key, low - share, "below"))
    return sorted(out, key=lambda x: -x[1])


def balance_score(shares: dict[str, float]) -> int:
    """Бал 1–10. 10 — усі категорії в межах орієнтирів."""
    if not shares:
        return 0
    total = sum(points for _key, points, _side in deviations(shares))
    return max(1, min(10, round(10 - total / DEVIATION_DIVISOR)))


def headline(shares: dict[str, float], score: int) -> str:
    """Одне речення «чому» — про найбільше відхилення, без моралі."""
    if not shares:
        return "Ще замало даних, щоб оцінити структуру покупок."
    gaps = deviations(shares)
    if not gaps:
        return "Структура витрат на їжу тримається в межах орієнтирів."

    key, _points, side = gaps[0]
    label = cats.CATEGORY_LABELS.get(key, key).lower()
    share = round(shares.get(key, 0.0))
    low, high = cats.TARGET_SHARES[key]
    if side == "above":
        return f"Найбільше вибивається «{label}» — {share}% витрат на їжу проти орієнтира до {round(high)}%."
    return f"Найменше у кошику «{label}» — {share}% проти орієнтира від {round(low)}%."


def macros_from_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Зводить БЖВ по МАСІ, а не середнім по товарах.

    Товар без харчової цінності не входить у розрахунок і не підставляється
    нулями — інакше профіль поїхав би в бік «здорового».
    """
    items = (plan or {}).get("items") or []
    active = [i for i in items if i.get("action") != "blocked"]
    covered: list[dict[str, Any]] = []
    grams_total = 0.0
    totals = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}

    for item in active:
        detail = item.get("detail") or {}
        nutrition = detail.get("nutrition") or {}
        if nutrition.get("kcal") is None:
            continue
        weight = detail.get("weight_g")
        if not weight:
            continue
        grams = float(weight) * float(item.get("quantity") or 1)
        grams_total += grams
        for key, field in (("kcal", "kcal"), ("protein", "protein"),
                           ("fat", "fat"), ("carbs", "carbs")):
            value = nutrition.get(field)
            if value is not None:
                totals[key] += float(value) * grams / 100
        covered.append(item)

    coverage = len(covered) / len(active) if active else 0.0
    per_100g = (
        {key: round(value / grams_total * 100, 1) for key, value in totals.items()}
        if grams_total else {}
    )
    return {
        "covered": len(covered),
        "total": len(active),
        "coverage_pct": round(coverage * 100),
        "grams": round(grams_total),
        "per_100g": per_100g,
        "totals": {key: round(value) for key, value in totals.items()},
        "enough_for_daily": coverage >= MIN_COVERAGE_FOR_DAILY,
    }


def narrow_nutrients(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Цукор і сіль. Каталог Сільпо їх майже ніколи не віддає — кажемо чесно."""
    items = (plan or {}).get("items") or []
    found = {"sugar": [], "salt": []}
    for item in items:
        nutrition = ((item.get("detail") or {}).get("nutrition")) or {}
        for key in found:
            if nutrition.get(key) is not None:
                found[key].append({"name": item.get("name"), "per_100g": nutrition[key]})
    return {
        "sugar": found["sugar"],
        "salt": found["salt"],
        "note": (
            "Каталог Сільпо здебільшого не публікує вміст цукру й солі. "
            "Ми показуємо лише те, що справді прийшло в даних, і не "
            "підставляємо нулі замість відсутніх значень."
        ),
    }


def build(orders, plan: dict[str, Any] | None, goal: str | None, period: str) -> dict[str, Any]:
    """Повний payload екрана «Харчування» для обраного періоду."""
    days = PERIODS.get(period, 7)
    if not orders:
        return {"has_data": False, "reason": "Чеків Сільпо поки не знайшли"}

    if days is not None:
        cutoff = orders[0].created_at - timedelta(days=days)
        window = [o for o in orders if o.created_at >= cutoff]
    else:
        window = list(orders)
    if not window:
        return {"has_data": False, "reason": f"За {PERIOD_LABELS.get(period, period)} чеків немає"}

    lines = [line for order in window for line in order.items]
    structure = cats.analyse(lines, goal)
    shares = plate_shares(structure)
    score = balance_score(shares)

    plate_spend = sum(
        c.spend for c in structure.categories if c.key in PLATE_CATEGORIES
    )
    total_spend = structure.total_spend or 1.0

    return {
        "has_data": True,
        "period": {
            "key": period,
            "label": PERIOD_LABELS.get(period, period),
            "days": days,
            "receipts": len(window),
        },
        "score": score,
        "sentence": headline(shares, score),
        "plate": {
            "shares": [
                {
                    "key": key,
                    "label": cats.CATEGORY_LABELS.get(key, key),
                    "share": round(shares.get(key, 0.0), 1),
                    "target_min": cats.TARGET_SHARES[key][0],
                    "target_max": cats.TARGET_SHARES[key][1],
                    "status": (
                        "above" if shares.get(key, 0.0) > cats.TARGET_SHARES[key][1]
                        else "below" if shares.get(key, 0.0) < cats.TARGET_SHARES[key][0]
                        else "ok"
                    ),
                }
                for key in PLATE_CATEGORIES
            ],
            "food_share_of_spend": round(plate_spend / total_spend * 100, 1),
        },
        "categories": structure.as_dict(),
        "recommendations": recommendations(structure),
        "macros": macros_from_plan(plan),
        "narrow": narrow_nutrients(plan),
    }


# --- Пасивний чіп корисності кошика ---------------------------------------
# Свідомо той самий метод, що й на екрані «Харчування»: два різні бали в
# одному застосунку — це два різні пояснення, які довелось би захищати.
# Рахується з назв товарів, без жодного виклику MCP, тому миттєво.
def cart_rating(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    food = [
        i for i in items
        if cats.categorize(i.get("name") or "") in PLATE_CATEGORIES
    ]
    if not food:
        return None

    lines = [
        {"name": i.get("name"), "price": i.get("price"), "quantity": i.get("quantity")}
        for i in items
    ]
    shares = plate_shares(cats.analyse(lines))
    score = balance_score(shares)
    gaps = deviations(shares)

    if score >= 8:
        tone, label = "good", "Кошик збалансований"
    elif score >= 5:
        tone, label = "neutral", "Кошик прийнятний"
    else:
        tone, label = "watch", "Структура перекошена"

    if gaps:
        key, _points, side = gaps[0]
        name = cats.CATEGORY_LABELS.get(key, key).lower()
        label = f"{label} · {'багато' if side == 'above' else 'мало'} «{name}»"

    return {"score": score, "tone": tone, "label": label, "food_items": len(food)}
