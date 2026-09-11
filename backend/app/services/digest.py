"""Дайджест у бота: що час поповнити і що подешевшало.

Правило частоти прямо з опитування й нашої ж специфікації: в режимі
«автопілот» — не частіше разу на тиждень, бо цей режим для тих, хто не хоче
взаємодіяти. В решті режимів — не частіше разу на добу.

Мовчання є валідним результатом: якщо нема ні поповнень, ні падінь цін,
дайджест не надсилається взагалі. Порожнє сповіщення гірше за жодне.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.bot import telegram_api
from app.bot.report import miniapp_keyboard
from app.db import repo
from app.services import cycles, pipeline, price_watch

log = logging.getLogger("digest")

# Мінімальний проміжок між дайджестами за режимом
MIN_GAP_HOURS = {"auto": 24 * 7, "saving": 24, "health": 24 * 7, "analytics": 24 * 365}
DEFAULT_GAP_HOURS = 24

MAX_LINES = 4
# Як часто прокидається фонова задача
SWEEP_INTERVAL_SECONDS = 6 * 3600


def _gap_hours(mode: str | None) -> int:
    return MIN_GAP_HOURS.get(mode or "auto", DEFAULT_GAP_HOURS)


def due_for_digest(sent_at: Any, mode: str | None, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if not sent_at:
        return True
    when = sent_at if isinstance(sent_at, datetime) else datetime.fromisoformat(str(sent_at))
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return now - when >= timedelta(hours=_gap_hours(mode))


def compose(due: list[dict[str, Any]], drops: list[dict[str, Any]]) -> str | None:
    """Текст дайджесту. None означає «нема про що писати» — і це нормально."""
    blocks: list[str] = []
    if due:
        lines = [cycles.digest_line(r) for r in due[:MAX_LINES]]
        more = len(due) - len(lines)
        if more > 0:
            lines.append(f"…і ще {more}")
        blocks.append("🧺 <b>Час поповнити</b>\n" + "\n".join(lines))
    if drops:
        lines = [price_watch.digest_line(d) for d in drops[:MAX_LINES]]
        total = round(sum(d["saved"] for d in drops))
        blocks.append(f"💰 <b>Подешевшало</b> (−{total} ₴)\n" + "\n".join(lines))
    if not blocks:
        return None
    return "\n\n".join(blocks)


async def send_to_user(user_id: str, force: bool = False) -> dict[str, Any]:
    """Збирає й надсилає дайджест одному гостю."""
    user = await repo.get_user(user_id)
    if not user or not user.get("telegram_id"):
        return {"sent": False, "reason": "немає telegram_id"}

    goal_row = await repo.get_goal(user_id) or {}
    if not force and not due_for_digest(goal_row.get("digest_sent_at"), goal_row.get("mode")):
        return {"sent": False, "reason": "надто рано за режимом гостя"}

    plan = pipeline.cached_plan(user_id)
    if not plan or not plan.get("has_data"):
        plan = await pipeline.build_plan(user_id)
        if not plan.get("has_data"):
            return {"sent": False, "reason": plan.get("reason", "немає даних")}

    items = plan.get("items") or []
    stored_cycles = await repo.cycles_for(user_id)
    due = cycles.build(items, stored_cycles)["due"]
    # Сповіщаємо лише про те, на що гість сам підписався
    due = [r for r in due if r["reminder_on"]]

    snapshot = await repo.price_snapshot(user_id)
    watch = price_watch.compare(items, snapshot)
    await repo.save_price_snapshot(user_id, watch["snapshot"])

    text = compose(due, watch["drops"])
    if not text:
        return {"sent": False, "reason": "нема про що писати"}

    await telegram_api.send_message(
        int(user["telegram_id"]), text, reply_markup={"inline_keyboard": miniapp_keyboard()}
    )
    # save_prefs, а не save_goal: у гостя може ще не бути рядка налаштувань,
    # і save_goal упав би на NOT NULL для goal.
    await repo.save_prefs(user_id, {"digest_sent_at": datetime.now(UTC).isoformat()})
    return {"sent": True, "due": len(due), "drops": len(watch["drops"])}


async def run_once() -> dict[str, Any]:
    """Один прохід по всіх під'єднаних гостях."""
    results = {"checked": 0, "sent": 0}
    for row in await repo.users_with_tokens():
        results["checked"] += 1
        try:
            outcome = await send_to_user(row["user_id"])
            if outcome.get("sent"):
                results["sent"] += 1
        except Exception as exc:  # noqa: BLE001 — один гість не має валити прохід
            log.warning("дайджест для %s не пройшов: %s", row["user_id"], exc)
    return results


async def sweep_forever() -> None:
    """Фонова задача застосунку. Падіння окремого проходу не зупиняє цикл."""
    while True:
        try:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            log.info("дайджест: прохід — %s", await run_once())
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("прохід дайджесту впав: %s", exc)
