"""Спільна точка входу до побудови плану — і політика його оновлення.

ПРАВИЛО: результат перебудовується лише у двох випадках —
  1. гість сам натиснув «оновити»;
  2. фонова перевірка побачила НОВИЙ чек.

Просто відкрити застосунок недостатньо. Повна побудова коштує понад тридцять
викликів MCP і чверть хвилини; показувати за ці гроші те саме — марнотратство.

Перевірка новизни теж не безкоштовна (три-чотири виклики), тому вона:
  * ніколи не блокує відповідь — летить у фон уже після того, як гість
    побачив збережені дані;
  * запускається не частіше, ніж раз на PROBE_INTERVAL.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.db import repo
from app.mcp.gateway import silpo
from app.agent import analyst
from app.services import cache, decisions, freshness, habits, jobs, modes, opportunities
from app.services import plan as plan_service
from app.services import pricing
from app.services.cart_analysis import fetch_cart

log = logging.getLogger("pipeline")

PLAN_JOB = "plan_next"
# Як часто взагалі маємо право питати Сільпо, чи є новий чек
PROBE_INTERVAL_SECONDS = 6 * 3600

# Перевірки, що вже летять, — щоб паралельні відкриття не множили виклики
_probing: set[str] = set()

# Реальна фаза побудови для екрана очікування. Саме фаза, а не вигаданий
# відсоток: показувати «73%» там, де ми не знаємо загального обсягу, — брехня.
_phase: dict[str, str] = {}

PHASES = {
    "receipts": "Читаю ваші покупки за рік…",
    "habits": "Шукаю, що ви берете за звичкою…",
    "prices": "Перевіряю поточні ціни й акції…",
    "agent": "Готую план наступної покупки…",
}


def phase_of(user_id: str) -> str | None:
    return _phase.get(user_id)


def tolerance_from(goal_row: dict[str, Any]) -> Any:
    """Поріг гостя. Порожній рядок у базі — це «не налаштовував», а не «без обмежень»."""
    if "price_tolerance" in goal_row and goal_row.get("mode"):
        return goal_row["price_tolerance"]
    return pricing.DEFAULT_TOLERANCE


async def build_plan(user_id: str) -> dict[str, Any]:
    """Одна повна побудова. Дорога — тому викликається лише через ensure_plan."""
    goal_row = await repo.get_goal(user_id) or {}
    _phase[user_id] = PHASES["receipts"]
    async with silpo(user_id) as api:
        ctx, _cart, meta = await fetch_cart(api)
        if ctx is None:
            _phase.pop(user_id, None)
            return {"has_data": False, "reason": meta.get("reason", "Дані Сільпо недоступні")}
        orders = await habits.fetch_offline_orders(api, ctx)
        _phase[user_id] = PHASES["prices"]
        plan = await plan_service.build(
            api, ctx, orders, goal_row.get("goal"), tolerance_from(goal_row),
            classifier=analyst.classify,
        )

    _phase[user_id] = PHASES["agent"]
    if plan.get("has_data"):
        plan = await decisions.attach(user_id, plan)
        # Модель бачить уже пораховані факти й додає до них судження.
        # Її недоступність нічого не ламає: план лишається повним.
        agent = await analyst.analyse(plan)
        # Кроки міркування лишаються в логах, але НЕ віддаються в інтерфейс:
        # гостю потрібні перевірювані підстави, а не токени роздумів моделі.
        agent.pop("steps", None)
        plan["agent"] = agent
        # Спершу режим гостя задає подачу, потім агент уточнює — але лише
        # там, де режим це дозволяє. В «економії» гроші мають бути першими
        # незалежно від того, що вирішила модель.
        modes.apply(plan, goal_row.get("mode"))
        _apply_agent(plan)
        # Можливості — це та сама знахідка, подана як відповідь на питання
        # «що ти для мене знайшов?». Докази — замість ходу думки моделі.
        plan["opportunities"] = opportunities.build(plan)
        for item in plan.get("items") or []:
            item["evidence"] = opportunities.evidence_for(item)
        plan["signature"] = freshness.signature_from(orders)
        await cache.store(user_id, PLAN_JOB, plan["signature"], plan)
    _phase.pop(user_id, None)
    return plan


def _apply_agent(plan: dict[str, Any]) -> None:
    """Вплітає судження моделі у план — там, де воно щось додає."""
    agent = plan.get("agent") or {}
    if not agent.get("available"):
        return

    verdicts = agent.get("verdicts") or {}
    swaps = agent.get("swaps") or {}
    for item in plan.get("items") or []:
        slug = item.get("slug")
        if slug in verdicts:
            item["agent_why"] = verdicts[slug]["why"]
        judged = swaps.get(slug)
        if judged and not judged["keep"] and item.get("alternative"):
            # Модель каже, що таку заміну не купиш. Прибираємо пропозицію,
            # але пояснення лишаємо — гість має бачити, чому її немає.
            item["alternative_rejected"] = {
                "name": item["alternative"].get("name"), "why": judged["why"],
            }
            item["alternative"] = None
            if item.get("action") in ("switch", "review"):
                item["action"] = "keep"

    order = agent.get("order") or []
    if order and modes.get((plan.get("summary") or {}).get("mode")).agent_may_reorder:
        rank = {kind: i for i, kind in enumerate(order)}
        plan["findings"] = sorted(
            plan.get("findings") or [],
            key=lambda f: rank.get(f.get("kind"), len(rank)),
        )


async def _probe_and_refresh(user_id: str, known_signature: str | None) -> None:
    """Фонова перевірка новизни. Перебудовує ЛИШЕ якщо чеки справді змінились."""
    try:
        async with silpo(user_id) as api:
            ctx, _cart, _meta = await fetch_cart(api)
            if ctx is None:
                return
            signature = await freshness.probe(api, ctx)
        if signature is None:
            return
        if signature == known_signature:
            await cache.touch(user_id, PLAN_JOB)
            return

        log.info("нові чеки в %s — перебудовуємо", user_id)
        # Похідні (аналітика, харчування) зроблені з тих самих чеків
        await cache.drop_all(user_id)
        for name in (PLAN_JOB, "insights", "usual", "nutrition:week",
                     "nutrition:month", "nutrition:all"):
            jobs.invalidate(name, user_id)
            jobs.reset_failures(name, user_id)
        await build_plan(user_id)
    except Exception as exc:  # noqa: BLE001 — перевірка не має нічого ламати
        log.warning("перевірка новизни для %s не вдалась: %s", user_id, exc)
    finally:
        _probing.discard(user_id)


def _schedule_probe(user_id: str, row: dict[str, Any]) -> bool:
    """Ставить перевірку у фон, якщо востаннє питали давно. True — поставили."""
    if user_id in _probing:
        return False
    age = cache.age_seconds(row, "checked_at")
    if age is not None and age < PROBE_INTERVAL_SECONDS:
        return False
    _probing.add(user_id)
    asyncio.create_task(_probe_and_refresh(user_id, row.get("signature")))
    return True


def _served(row: dict[str, Any], checking: bool) -> dict[str, Any]:
    payload = dict(row.get("payload") or {})
    payload["cached"] = True
    payload["built_at"] = row.get("built_at")
    payload["checked_at"] = row.get("checked_at")
    payload["checking_for_updates"] = checking
    return payload


async def ensure_plan(user_id: str, refresh: bool = False) -> dict[str, Any]:
    """Збережений план миттєво; повна побудова — лише на вимогу або по новому чеку."""
    if refresh:
        await cache.drop_all(user_id)
        for name in (PLAN_JOB, "insights", "usual", "nutrition:week",
                     "nutrition:month", "nutrition:all"):
            jobs.invalidate(name, user_id)
            jobs.reset_failures(name, user_id)
    else:
        row = await cache.load(user_id, PLAN_JOB)
        if row and row.get("payload"):
            return _served(row, _schedule_probe(user_id, row))

    result = await jobs.cached_or_start(PLAN_JOB, user_id, lambda: build_plan(user_id))
    if result.get("building"):
        result = {**result, "phase": phase_of(user_id) or PHASES["receipts"]}
    return result


def cached_plan(user_id: str) -> dict[str, Any] | None:
    """Синхронний доступ для тих, хто вже точно знає, що план побудовано."""
    return jobs.get_cached(PLAN_JOB, user_id)


async def cached_plan_async(user_id: str) -> dict[str, Any] | None:
    """Памʼять процесу, а якщо там порожньо — збережене в базі."""
    hot = jobs.get_cached(PLAN_JOB, user_id)
    if hot:
        return hot
    row = await cache.load(user_id, PLAN_JOB)
    return row.get("payload") if row else None
