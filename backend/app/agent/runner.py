"""Запуск агента: модель оркеструє, код рахує.

Відповідь на питання журі «а навіщо тут LLM?» має бути видимою у трейсі:
модель сама вирішує, що спитати в історії покупок, які товари шукати, які
порівняти й що покласти в кошик. Правила такого не вміють — вони можуть лише
виконати заздалегідь описану послідовність.

Що модель НЕ робить: не рахує ціни, частки, економію й оцінки товарів.
Усі числа приходять із інструментів, тобто з коду.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.agent.toolset import AgentSession, build_tools
from app.llm.provider import LLMUnavailable, Step, get_provider
from app.mcp import tools as T
from app.mcp.gateway import silpo
from app.services.cart_analysis import fetch_cart

log = logging.getLogger("agent")

MAX_STEPS = 14

SYSTEM = """Ти — агент, який складає продуктовий кошик для гостя супермаркету Сільпо.

Твоя робота — не порадити, а ЗІБРАТИ кошик. Гість не має нічого шукати сам.

Порядок дій, якого варто триматись:
1. get_profile — дізнайся ціль, обмеження й бюджет гостя.
2. get_purchase_history — подивись, що людина реально купує і яка структура
   витрат за категоріями. Це твій головний контекст.
3. get_promotions — подивись, що зараз в акції та які є купони.
4. Виріши, ЩО саме треба змінити в структурі покупок під ціль гостя.
5. find_products — знайди конкретні товари. Спирайся на те, що гість уже
   купує: не пропонуй кіноа людині, яка бере картоплю.
6. inspect_product — перевір спірні варіанти перед вибором.
7. add_to_draft — збери кошик, стежачи за бюджетом у підсумках.
8. get_draft — перевір результат перед відповіддю.

Жорсткі правила:
- Заміна зберігає РОЛЬ товару. Кола → Кола Zero чи інший напій без цукру,
  але НЕ вода замість коли і НЕ броколі замість чіпсів.
- Заміна не має бути помітно дорожчою за оригінал.
- За інших рівних обирай те, що зараз в акції — гість економить.
- Ніколи не пропонуй товар, що конфліктує з обмеженнями гостя.
- Не рахуй жодних чисел самостійно: суми, частки й економію повертають
  інструменти. Не вигадуй калорійність чи склад.
- Ти не лікар: не став діагнозів і не призначай дієт. Ти оптимізуєш структуру
  покупок під ціль, яку обрав сам гість.

У фінальній відповіді: 2–4 короткі речення українською — що ти зібрав,
чому саме так, скільки вийшло і скільки економія. Без переліку всіх товарів,
без markdown, без емодзі."""


@dataclass
class AgentRun:
    prompt: str
    answer: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    draft: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    provider: str = "none"
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt, "answer": self.answer, "steps": self.steps,
            "draft": self.draft, "summary": self.summary,
            "duration_ms": self.duration_ms, "provider": self.provider, "error": self.error,
        }


# Людські підписи кроків для UI: гість бачить дію, а не назву функції
STEP_LABELS = {
    "get_profile": ("Прочитано вашу ціль", "мета й обмеження"),
    "get_purchase_history": ("Отримано історію покупок", "чеки Сільпо"),
    "get_promotions": ("Знайдено актуальні акції", "включно з вашими купонами"),
    "find_products": ("Підібрано товари в магазині", "пошук у каталозі"),
    "inspect_product": ("Перевірено склад товару", "склад, алергени, оцінка"),
    "add_to_draft": ("Додано в кошик", ""),
    "remove_from_draft": ("Прибрано з кошика", "не вписалось у бюджет"),
    "get_draft": ("Кошик перевірено", "сума й структура"),
}


def humanize(step: Step, session: AgentSession) -> dict[str, Any] | None:
    """Перетворює технічний крок на рядок, який не соромно показати гостю."""
    if step.kind == "think":
        return None                      # внутрішні міркування не показуємо
    if step.kind == "answer":
        return None
    title, subtitle = STEP_LABELS.get(step.tool or "", (step.tool or "Дія", ""))

    if step.tool == "get_purchase_history" and session.history_cache:
        h = session.history_cache
        subtitle = f"{h['receipts']} чеків за {h['period_days']} днів"
    elif step.tool == "find_products":
        queries = step.args.get("queries") or []
        subtitle = f"{len(queries)} запит(ів) у каталозі"
    elif step.tool == "add_to_draft":
        subtitle = step.args.get("reason") or ""
        title = f"Додано: {step.args.get('slug', '')[:40]}"
    elif step.tool == "get_promotions" and session.promo_cache is not None:
        subtitle = f"{len(session.promo_cache)} акцій у вашому магазині"

    return {"title": title, "subtitle": subtitle, "tool": step.tool}


async def run(user_id: str, prompt: str, profile: dict[str, Any]) -> AgentRun:
    started = time.monotonic()
    result = AgentRun(prompt=prompt, provider=get_provider().name)

    async with silpo(user_id) as api:
        ctx, _cart, meta = await fetch_cart(api)
        if ctx is None:
            result.error = meta.get("reason", "Кошик Сільпо недоступний")
            return result

        session = AgentSession(api, ctx, profile)
        tools = build_tools(session)

        try:
            answer, steps = await get_provider().run_agent(
                SYSTEM, prompt, tools, max_steps=MAX_STEPS
            )
        except LLMUnavailable as exc:
            result.error = str(exc)
            return result
        except Exception as exc:  # noqa: BLE001
            log.exception("агент впав")
            result.error = str(exc)[:300]
            return result

    result.answer = answer
    result.steps = [s for s in (humanize(step, session) for step in steps) if s]
    result.draft = session.draft
    result.summary = session.draft_summary()
    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result
