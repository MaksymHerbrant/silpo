"""Форматування push-звіту по кошику для чату Telegram."""
from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.nutrition.score import AMDR

LIGHTS = {"ok": "🟢", "warn": "🟡", "bad": "🔴"}
MACRO_LABELS = {"protein": "Білки", "fat": "Жири", "carbs": "Вуглеводи"}


def _light(macro: str, deviation: float) -> str:
    if deviation <= 0:
        return LIGHTS["ok"]
    return LIGHTS["warn"] if deviation <= 10 else LIGHTS["bad"]


def cart_report(analysis: dict[str, Any]) -> str:
    """Короткий звіт-світлофор — те, що бачить користувач у чаті."""
    if analysis.get("empty"):
        return f"🛒 <b>Кошик порожній</b>\n{analysis.get('reason', '')}"

    items = analysis.get("items", [])
    shares = analysis.get("shares", {})
    deviations = analysis.get("deviations", {})
    totals = analysis.get("totals", {})

    lines = [
        f"🛒 <b>Ваш кошик — {len(items)} товар(ів)</b>",
        f"Оцінка балансу: <b>{analysis.get('score')}/100</b> (клас {analysis.get('letter')})",
        "",
    ]
    for macro, label in MACRO_LABELS.items():
        low, high = AMDR[macro]
        share = shares.get(macro, 0)
        deviation = deviations.get(macro, 0)
        status = "норма" if deviation <= 0 else (
            f"нижче норми ({low:.0f}–{high:.0f}%)" if share < low else f"перевищення (норма {low:.0f}–{high:.0f}%)"
        )
        lines.append(f"{_light(macro, deviation)} {label}: {share}% енергії — {status}")

    worst = sorted(
        [i for i in items if i.get("score") is not None], key=lambda i: i["score"]
    )[:1]
    if worst:
        lines += ["", f"⚠️ Найбільше псує баланс: <b>{worst[0]['title']}</b> ({worst[0]['score']}/100)"]

    warnings = analysis.get("allergen_warnings") or []
    if warnings:
        names = ", ".join(sorted({w["restriction"] for w in warnings}))
        lines.append(f"🚫 Ваші обмеження в кошику: {names}")

    lines += [
        "",
        f"Разом: {totals.get('calories', 0)} ккал · {totals.get('mass_g', 0)} г · {totals.get('price', 0)} грн",
    ]
    return "\n".join(lines)


def swap_offer(swap: dict[str, Any]) -> str:
    price_note = ""
    old_price, new_price = swap.get("original_price"), swap.get("suggested_price")
    if old_price and new_price:
        diff = round(new_price - old_price, 2)
        price_note = (
            " Ціна майже та сама." if abs(diff) < 5
            else f" Різниця в ціні: {'+' if diff > 0 else ''}{diff} грн."
        )
    own = " Це власна марка Сільпо." if swap.get("is_own_brand") else ""
    return (
        f"💡 Замість <b>{swap['original_title']}</b> можна взяти "
        f"<b>{swap['suggested_title']}</b>.\n\n{swap['reason']}.{price_note}{own}"
    )


def swap_keyboard(swap_id: str, price_delta: float | None = None) -> list[list[dict]]:
    label = "🔄 Замінити"
    if price_delta:
        label += f" ({'+' if price_delta > 0 else ''}{round(price_delta)} грн)"
    return [[
        {"text": label, "callback_data": f"swap:{swap_id}:apply"},
        {"text": "❌ Залишити", "callback_data": f"swap:{swap_id}:skip"},
    ]]


def miniapp_keyboard() -> list[list[dict]]:
    url = get_settings().public_backend_url.rstrip("/")
    return [[{"text": "Відкрити GreenCart", "web_app": {"url": url}}]]


def profile_report(trend: dict[str, Any]) -> str:
    """Звіт за чеками — коли кошик порожній (типовий випадок)."""
    profile = trend.get("profile")
    habits = trend.get("habits") or {}
    summary = habits.get("summary")
    if not profile or not summary:
        return (
            "🧾 <b>Поки що нема чого аналізувати</b>\n"
            "Ми не знайшли ваших чеків Сільпо за останні місяці."
        )

    shares = profile.get("shares", {})
    deviations = profile.get("deviations", {})
    lines = [
        f"📊 <b>Ваш нутрі-профіль</b> — {summary['orders_count']} чеків "
        f"за {summary['period_days']} днів",
        f"Оцінка раціону: <b>{profile['score']}/100</b> (клас {profile['letter']})",
        "",
    ]
    for macro, label in MACRO_LABELS.items():
        low, high = AMDR[macro]
        share = shares.get(macro, 0)
        deviation = deviations.get(macro, 0)
        status = "норма" if deviation <= 0 else (
            f"нижче норми ({low:.0f}–{high:.0f}%)" if share < low
            else f"перевищення (норма {low:.0f}–{high:.0f}%)"
        )
        lines.append(f"{_light(macro, deviation)} {label}: {share}% енергії — {status}")

    categories = habits.get("categories") or []
    watch = [c for c in categories if c["name"] in ("Солодкі напої", "Солодке й снеки", "Алкоголь")]
    if watch:
        parts = ", ".join(f"{c['name'].lower()} {c['share']}%" for c in watch[:3])
        lines += ["", f"💸 Частка витрат: {parts}"]

    lines += [
        "",
        f"Середній чек {summary['avg_check']} ₴ · {summary['visits_per_week']} візити на тиждень",
        f"Зекономлено на акціях: {round(summary['total_saved'])} ₴",
    ]
    return "\n".join(lines)
