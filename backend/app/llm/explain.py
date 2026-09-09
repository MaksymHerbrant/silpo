"""Пояснювальні тексти від Claude.

ЖОРСТКЕ ПРАВИЛО: LLM не рахує жодних чисел. Скор, БЖУ, цукор і дельти
обчислені детерміновано в app/nutrition/. Claude отримує вже готові числа і
лише переформульовує їх людською мовою українською. Якщо ключа немає або
запит впав — використовується детермінований шаблон (сервіс не падає).
"""
from __future__ import annotations

import json
from typing import Any

from app.config import get_settings

SYSTEM = (
    "Ти — дружній нутриціоніст-помічник у застосунку «Нутрі-Кошик». "
    "Тобі дають ГОТОВІ, вже обчислені числа про кошик покупок. "
    "Категорично заборонено вигадувати, перераховувати або змінювати будь-які "
    "числа: використовуй лише ті, що є у вхідних даних, і лише за потреби. "
    "Пиши українською, 2–3 короткі речення, без емодзі, без медичних діагнозів "
    "і без слова «дієта». Тон — спокійний і підбадьорливий."
)

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


def _fallback_summary(analysis: dict[str, Any]) -> str:
    score = analysis.get("score")
    letter = analysis.get("letter")
    sugar = (analysis.get("totals") or {}).get("added_sugar")
    parts = [f"Рейтинг вашого кошика — {score}/100 (клас {letter})."]
    if sugar:
        parts.append(f"Доданого цукру в кошику приблизно {sugar} г.")
    worst = [i for i in analysis.get("items", []) if i.get("score") is not None]
    if worst:
        worst.sort(key=lambda i: i["score"])
        parts.append(f"Найбільше знижує оцінку: {worst[0]['title']}.")
    return " ".join(parts)


async def summarize_cart(analysis: dict[str, Any]) -> str:
    """Коротке пояснення до рейтингу кошика."""
    s = get_settings()
    if not (s.enable_llm_explanations and s.anthropic_api_key):
        return _fallback_summary(analysis)

    facts = {
        "score_0_100": analysis.get("score"),
        "letter": analysis.get("letter"),
        "per_100g": analysis.get("per_100g"),
        "totals": analysis.get("totals"),
        "coverage": analysis.get("coverage"),
        "worst_items": [
            {"title": i["title"], "score": i["score"], "sugar_per_100g": (i.get("nutrition") or {}).get("sugar")}
            for i in sorted(
                [i for i in analysis.get("items", []) if i.get("score") is not None],
                key=lambda i: i["score"],
            )[:3]
        ],
        "allergen_warnings": [w["restriction"] for w in analysis.get("allergen_warnings", [])][:3],
    }
    try:
        resp = await _get_client().messages.create(
            model=s.anthropic_model,
            max_tokens=400,
            system=SYSTEM,
            output_config={"effort": "low"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Дані аналізу кошика (числа вже обчислені, не змінюй їх):\n"
                        + json.dumps(facts, ensure_ascii=False)
                        + "\n\nНапиши коротке пояснення для користувача."
                    ),
                }
            ],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return text or _fallback_summary(analysis)
    except Exception:  # noqa: BLE001 — пояснення не критичне для сценарію
        return _fallback_summary(analysis)


def swap_reason(target: dict[str, Any], candidate, own_brand: bool) -> str:  # noqa: C901
    """Детермінований (без LLM) текст причини заміни.

    Викликається у циклі побудови свопів, тому має бути миттєвим і дешевим;
    «оживлення» тексту робить summarize_cart на рівні екрана.
    """
    reasons: list[str] = []
    t_nutr = target.get("nutrition") or {}
    c_nutr = candidate.nutrition
    if c_nutr and t_nutr.get("energy_kcal") and c_nutr.energy_kcal:
        diff = t_nutr["energy_kcal"] - c_nutr.energy_kcal
        if diff >= 15:
            reasons.append(f"на {round(diff)} ккал менше на 100 г")
    if c_nutr and c_nutr.protein and (t_nutr.get("protein") or 0) < c_nutr.protein:
        reasons.append(f"більше білка ({c_nutr.protein} г на 100 г)")
    if c_nutr and t_nutr.get("fat") and c_nutr.fat is not None:
        diff = t_nutr["fat"] - c_nutr.fat
        if diff >= 3:
            reasons.append(f"на {round(diff, 1)} г менше жиру")
    if own_brand:
        reasons.append("власна марка Сільпо")
    gain = (candidate.score or 0) - (target.get("score") or 0)
    head = f"+{gain} балів до рейтингу кошика"
    return head + (": " + ", ".join(reasons) if reasons else "")


async def upsell_text(analysis: dict[str, Any], swap: dict[str, Any]) -> str:
    """Позитивний upsell для чату: Claude формулює, числа рахуємо ми.

    LLM отримує готові цифри (оцінки, різницю, ціну) і лише перетворює їх на
    людське речення. Якщо ключа немає або запит впав — детермінований текст.
    """
    from app.bot import report as report_fmt

    fallback = report_fmt.swap_offer(swap)
    s = get_settings()
    if not (s.enable_llm_explanations and s.anthropic_api_key):
        return fallback

    facts = {
        "basket_score": analysis.get("score"),
        "macro_shares_percent": analysis.get("shares"),
        "deviation_from_who_ranges_pp": analysis.get("deviations"),
        "original": {
            "title": swap.get("original_title"),
            "score": swap.get("original_score"),
            "price": swap.get("original_price"),
        },
        "suggested": {
            "title": swap.get("suggested_title"),
            "score": swap.get("suggested_score"),
            "price": swap.get("suggested_price"),
            "is_silpo_own_brand": swap.get("is_own_brand"),
        },
        "computed_reason": swap.get("reason"),
    }
    try:
        resp = await _get_client().messages.create(
            model=s.anthropic_model,
            max_tokens=350,
            system=(
                SYSTEM + " Зараз ти пишеш коротке повідомлення в чат Telegram: вітання, "
                "у чому проблема з конкретним товаром, яка заміна і чим вона краща. "
                "Максимум 3 речення. Не використовуй markdown, лише простий текст. "
                "Жодних чисел, яких немає у вхідних даних."
            ),
            output_config={"effort": "low"},
            messages=[{
                "role": "user",
                "content": "Дані (числа вже обчислені, не змінюй їх):\n"
                           + json.dumps(facts, ensure_ascii=False),
            }],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return text or fallback
    except Exception:  # noqa: BLE001
        return fallback
