"""AI-порадник: що шукати на заміну і як скласти раціон.

Роль моделі — знання про їжу, яких немає в каталозі: чим люди насправді
замінюють колу, що кладуть у кошик на тиждень при наборі маси, що поєднується
між собою. Модель віддає СПИСОК ПОШУКОВИХ ЗАПИТІВ, а не рішення: далі ми
шукаємо ці товари в Сільпо, тягнемо харчову цінність і ціну, і відбір робить
детермінований код.

Тобто модель розширює простір варіантів, а математика його звужує.
Якщо LLM недоступний — усе працює на правилах із app/nutrition/rules.py.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.llm.provider import LLMUnavailable, get_provider
from app.nutrition.parser import ProductInfo

log = logging.getLogger("advisor")

SWAP_SYSTEM = (
    "Ти — досвідчений нутриціолог, який добре знає український продуктовий "
    "асортимент. Тобі дають товар, який гість купує регулярно, і його "
    "харчову цінність. Твоє завдання — запропонувати, ЧИМ його замінити.\n\n"
    "Жорсткі правила:\n"
    "1. Заміна виконує ТУ САМУ роль. Чіпси міняють на інший хрусткий снек "
    "(рисові чіпси, попкорн, кукурудзяні палички), а не на броколі. "
    "Солодкий напій — на інший напій. Ковбасу — на інше мʼясо.\n"
    "2. Заміна не має бути помітно дорожчою — це масовий продукт, не делікатес.\n"
    "3. Пиши назви так, як вони виглядають на цінниках у Сільпо: "
    "«Чіпси рисові», «Вода мінеральна негазована», «Йогурт грецький без цукру».\n"
    "4. Враховуй обмеження гостя, якщо вони вказані.\n"
    "5. Не рахуй жодних чисел — калорії й ціни ми порахуємо самі.\n\n"
    "Відповідай ЛИШЕ JSON без пояснень:\n"
    '{"problem": "коротко, у чому проблема товару",'
    ' "queries": ["запит 1", "запит 2", "запит 3", "запит 4", "запит 5"],'
    ' "reason": "чим заміна краща, одне речення"}'
)

PLAN_SYSTEM = (
    "Ти — нутриціолог, який складає продуктовий список на тиждень для гостя "
    "супермаркету Сільпо. Тобі дають ціль, добові норми, бюджет, обмеження і "
    "перелік товарів, які гість купує регулярно.\n\n"
    "Завдання: скласти СТРУКТУРУ тижневого раціону — які категорії продуктів "
    "і в якій приблизній кількості потрібні, і що саме шукати в магазині.\n\n"
    "Жорсткі правила:\n"
    "1. Спирайся на те, що гість уже їсть — не пропонуй кіноа людині, "
    "яка купує картоплю.\n"
    "2. Продукти мають бути дешевими й доступними: крупи, яйця, курка, "
    "сезонні овочі. Це список у супермаркет, а не в ресторан.\n"
    "3. Враховуй обмеження: якщо є глютен — жодного хліба й макаронів "
    "із пшениці.\n"
    "4. Назви пиши так, як на цінниках Сільпо.\n"
    "5. Не рахуй калорії, ціни й грами — це зробить наш код.\n\n"
    "Відповідай ЛИШЕ JSON:\n"
    '{"strategy": "одне речення про логіку цього тижня",'
    ' "groups": [{"role": "protein|carbs|veg|fruit|fat|snack",'
    ' "why": "нащо це в раціоні", "queries": ["назва 1", "назва 2", "назва 3"]}]}'
)


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


async def swap_queries(
    product: ProductInfo, restrictions: list[str], max_price: float | None
) -> dict[str, Any] | None:
    """Що шукати замість цього товару. None -> працюємо на правилах."""
    n = product.nutrition
    facts = {
        "назва": product.title,
        "бренд": product.brand,
        "ціна_грн": product.price,
        "максимальна_ціна_заміни_грн": round(max_price, 2) if max_price else None,
        "на_100_г": {
            "ккал": n.energy_kcal, "білки": n.protein, "жири": n.fat, "вуглеводи": n.carbs,
        },
        "рідина": product.is_liquid,
        "алкоголь": product.is_alcohol,
        "обмеження_гостя": restrictions,
    }
    try:
        raw = await get_provider().complete(
            SWAP_SYSTEM, json.dumps(facts, ensure_ascii=False), max_tokens=600
        )
    except LLMUnavailable:
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("advisor.swap_queries: %s", exc)
        return None

    data = _extract_json(raw)
    if not data or not isinstance(data.get("queries"), list):
        return None
    data["queries"] = [str(q)[:80] for q in data["queries"]][:6]
    return data


async def week_structure(
    targets: dict[str, Any],
    habit_titles: list[str],
    restrictions: list[str],
    budget: float | None,
    preferences: str | None,
    household: int,
) -> dict[str, Any] | None:
    """Структура тижневого раціону: ролі + що шукати. None -> правила."""
    facts = {
        "ціль": targets.get("goal_label"),
        "норми_на_день": {
            "ккал": targets.get("kcal"), "білки_г": targets.get("protein"),
            "жири_г": targets.get("fat"), "вуглеводи_г": targets.get("carbs"),
        },
        "людей_у_домі": household,
        "бюджет_на_тиждень_грн": budget,
        "обмеження": restrictions,
        "побажання_гостя": preferences,
        "що_купує_регулярно": habit_titles[:20],
    }
    try:
        raw = await get_provider().complete(
            PLAN_SYSTEM, json.dumps(facts, ensure_ascii=False), max_tokens=1200
        )
    except LLMUnavailable:
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("advisor.week_structure: %s", exc)
        return None

    data = _extract_json(raw)
    if not data or not isinstance(data.get("groups"), list):
        return None
    groups = []
    for group in data["groups"][:8]:
        if not isinstance(group, dict) or not isinstance(group.get("queries"), list):
            continue
        groups.append({
            "role": str(group.get("role", "other"))[:20],
            "why": str(group.get("why", ""))[:200],
            "queries": [str(q)[:80] for q in group["queries"]][:5],
        })
    if not groups:
        return None
    data["groups"] = groups
    return data


async def explain_plan(plan: dict[str, Any], targets: dict[str, Any]) -> str | None:
    """Людське пояснення до зібраного кошика. Числа — вже готові."""
    facts = {
        "ціль": targets.get("goal_label"),
        "покриття_норм_відсотки": plan.get("coverage_pct"),
        "сума_грн": plan.get("total_price"),
        "бюджет_грн": plan.get("budget"),
        "економія_на_акціях_грн": plan.get("total_saved"),
        "товари": [
            {"назва": i["title"], "кількість": i["quantity"], "роль": i["role"],
             "акція": i.get("on_promotion")}
            for i in plan.get("items", [])
        ],
    }
    system = (
        "Ти пояснюєш гостю, що ми поклали в його тижневий кошик і чому. "
        "2–3 короткі речення українською, без переліку всіх товарів, без емодзі. "
        "Використовуй ЛИШЕ ті числа, що є у вхідних даних — нічого не рахуй сам. "
        "Якщо покриття норм низьке, чесно про це скажи й поясни причину бюджетом."
    )
    try:
        text = await get_provider().complete(
            system, json.dumps(facts, ensure_ascii=False), max_tokens=350
        )
    except (LLMUnavailable, Exception):  # noqa: BLE001
        return None
    return text or None
