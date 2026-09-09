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

# Живий прогрес: кроки лягають сюди по мірі виконання, щоб Mini App показував
# їх у реальному часі, а не чекав 40 секунд на порожньому екрані.
_progress: dict[str, list[dict[str, Any]]] = {}


def live_steps(user_id: str) -> list[dict[str, Any]]:
    return list(_progress.get(user_id, []))


def reset_progress(user_id: str) -> None:
    _progress[user_id] = []

SYSTEM = """Ти — агент, який допомагає гостю Сільпо покращити його покупки.

ГОЛОВНЕ ПРАВИЛО: ти НІЧОГО не вирішуєш за гостя. Ти готуєш пропозиції з
варіантами, а обирає він. Твій результат — не заповнений кошик, а перелік
конкретних рішень, які гість може прийняти одним дотиком або відхилити.

Порядок роботи:
1. get_profile — ціль, обмеження, бюджет.
2. get_purchase_history — що гість РЕАЛЬНО купує. Це основа всього.
3. get_promotions — що зараз в акції.
4. Обери 3-5 товарів із тих, які гість купує НАЙЧАСТІШЕ і які найбільше
   суперечать його цілі.
5. Для кожного знайди через find_products 2-3 альтернативи ТІЄЇ САМОЇ
   смакової родини, перевір їх inspect_product і виклич propose_swap.
6. get_proposals — перевір, що вийшло.

Що таке «та сама смакова родина» (це найважливіше):
- Солодка газована кола → кола zero, інша газована без цукру, холодний чай.
  ВОДА — НЕ ЗАМІНА КОЛИ. Це інший продукт для іншої потреби.
- Чіпси → рисові чіпси, попкорн, кукурудзяні палички. НЕ овочі.
- Солодкий йогурт → йогурт без цукру того ж формату. НЕ сир.
- Пиво → безалкогольне пиво чи сидр. НЕ сік.
Заміна має бути такою, щоб гість не відчув, що його чогось позбавили.

Заборонено:
- Пропонувати товари дорожчі за оригінал більш ніж на чверть.
- Додавати «корисні» товари, яких гість не просив, лише тому що вони корисні.
  Банани, броколі й овочі «бо треба» — це повчання, а не допомога.
- Пропонувати те, що конфліктує з обмеженнями гостя.
- Рахувати будь-які числа самому: ціни й економію повертають інструменти.
- Ставити діагнози чи призначати дієти. Ти оптимізуєш покупки, ти не лікар.

propose_addition використовуй щонайбільше один раз і лише тоді, коли товар
справді доречний — наприклад, він зараз в акції і гість купував схоже раніше.

У фінальній відповіді: 2-3 короткі речення українською про те, що ти
пропонуєш і чому саме це. Без переліку всіх товарів, без markdown, без емодзі."""


@dataclass
class AgentRun:
    prompt: str
    answer: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    draft: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    provider: str = "none"
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt, "answer": self.answer, "steps": self.steps,
            "draft": self.draft, "proposals": self.proposals, "summary": self.summary,
            "duration_ms": self.duration_ms, "provider": self.provider, "error": self.error,
        }


# Людські підписи кроків для UI: гість бачить дію, а не назву функції
STEP_LABELS = {
    "propose_swap": ("Підготовлено варіанти заміни", ""),
    "propose_addition": ("Запропоновано доповнення", ""),
    "get_proposals": ("Пропозиції перевірено", ""),
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
    elif step.tool == "propose_swap":
        options = step.args.get("options") or []
        title = "Підготовлено варіанти заміни"
        subtitle = f"{len(options)} альтернатив(и) на вибір"
    elif step.tool == "propose_addition":
        title = "Запропоновано доповнення"
        subtitle = step.args.get("why", "")[:80]
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

        def on_step(step: Step) -> None:
            item = humanize(step, session)
            if item:
                _progress.setdefault(user_id, []).append(item)

        try:
            answer, steps = await get_provider().run_agent(
                SYSTEM, prompt, tools, max_steps=MAX_STEPS, on_step=on_step
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
    result.proposals = session.proposals
    result.summary = session.draft_summary()
    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result
