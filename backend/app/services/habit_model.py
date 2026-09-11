"""Що таке звичка — і чим вона відрізняється від збігу.

Претензія, з якої почалась ця модель: застосунок сказав людині, що вона
«регулярно бере сьомгу охолоджену», хоча вона брала її двічі — і недавно.
Це справедливо: рахувати повторення в короткому вікні означає плутати
звичку з випадковістю.

Звичка має ТРИ ознаки, і жодної з них окремо не досить:

  1. ПОВТОРЮВАНІСТЬ — куплено в кілька різних днів, а не кількома рядками
     в одному чеку. Вісім шматків форелі за один похід — це один похід.
  2. РОЗТЯГНУТІСТЬ У ЧАСІ — покупки розкидані по періоду, а не злиплись
     в один тиждень. Двічі за сусідні дні — це один епізод, не ритм.
  3. АКТУАЛЬНІСТЬ — звичка, яка обірвалась два місяці тому, вже не звичка.

Звідси чотири типи, і кожен заслуговує на різні слова в інтерфейсі:

  stable     стабільна звичка — можна впевнено класти в кошик
  emerging   нове: почали брати нещодавно, ритму ще немає
  fading     раніше брали регулярно, але давно не купували
  occasional випадкова або надто рідка покупка
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

# Скільки різних днів потрібно, щоб узагалі говорити про повторення
MIN_DAYS_FOR_REPEAT = 2
# Звичку міряємо СВІЖИМ вікном, а не всім періодом.
#
# Частка «у 25% тижнів періоду» не масштабується: на 12 тижнях це 3 тижні, а
# на 51 — уже 13, і річна історія парадоксально прибирала товари з кошика.
# Людина так не думає: «беру регулярно» означає «беру регулярно ЗАРАЗ»,
# а глибока історія лише додає впевненості, що це надовго.
RECENT_WINDOW_DAYS = 90
STABLE_MIN_DAYS = 3          # різних днів покупки у свіжому вікні
STABLE_MIN_WEEKS = 3         # і в стількох різних тижнях
# Покупки, злиплі в такому вікні, вважаємо ОДНИМ епізодом, а не ритмом
EPISODE_WINDOW_DAYS = 10
# Нещодавній старт: усі покупки в межах цього вікна від сьогодні
EMERGING_WINDOW_DAYS = 21
# Звичка вважається згаслою, якщо від останньої покупки минуло стільки циклів
FADING_CYCLES = 2.5

STABLE = "stable"
EMERGING = "emerging"
FADING = "fading"
OCCASIONAL = "occasional"

LABELS = {
    STABLE: "стабільна звичка",
    EMERGING: "нове у вашому кошику",
    FADING: "раніше брали регулярно",
    OCCASIONAL: "разова покупка",
}


@dataclass
class Habit:
    kind: str
    reason: str
    days: int                 # у скількох різних днях купували
    weeks: int                # у скількох різних тижнях
    span_days: int            # від першої покупки до останньої
    coverage: float           # частка тижнів періоду, у яких товар зʼявлявся
    since_last_days: int      # скільки днів минуло від останньої покупки
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "label": LABELS.get(self.kind, self.kind),
            "reason": self.reason, "days": self.days, "weeks": self.weeks,
            "span_days": self.span_days, "coverage": round(self.coverage, 2),
            "since_last_days": self.since_last_days,
        }


def _week(day: date) -> tuple[int, int]:
    iso = day.isocalendar()
    return iso[0], iso[1]


def analyse(
    days_iso: list[str], period_days: int, cycle_days: int, today: date | None = None
) -> Habit:
    """days_iso — дати покупок (по одній на день, не рядки чеків).

    Свіже вікно вирішує, чи це звичка ЗАРАЗ. Уся історія додає впевненості:
    товар, який людина бере рік, описується інакше, ніж той, що зʼявився
    минулого місяця, — навіть якщо в останньому кварталі вони однакові.
    """
    today = today or date.today()
    days = sorted({date.fromisoformat(d) for d in days_iso})

    if not days:
        return Habit(OCCASIONAL, "покупок не знайдено", 0, 0, 0, 0.0, 0)

    cutoff = today - timedelta(days=RECENT_WINDOW_DAYS)
    recent = [d for d in days if d >= cutoff]
    older = [d for d in days if d < cutoff]

    weeks = len({_week(d) for d in days})
    recent_weeks = len({_week(d) for d in recent})
    span = (days[-1] - days[0]).days
    window_weeks = max(round(min(period_days, RECENT_WINDOW_DAYS) / 7), 1)
    coverage = recent_weeks / window_weeks
    since_last = (today - days[-1]).days

    if len(days) < MIN_DAYS_FOR_REPEAT:
        return Habit(
            OCCASIONAL, "куплено за один похід — цього замало, щоб назвати звичкою",
            len(days), weeks, span, coverage, since_last,
        )

    # Ритм був, але обірвався: у свіжому вікні покупок майже немає
    if since_last > cycle_days * FADING_CYCLES and len(recent) < MIN_DAYS_FOR_REPEAT:
        months = max(round(span / 30), 1)
        tail = f", а до того брали {len(days)} разів за {months} міс." if older else ""
        return Habit(
            FADING, f"востаннє {since_last} дн. тому при циклі ~{cycle_days} дн.{tail}",
            len(days), weeks, span, coverage, since_last,
        )

    # Стабільна звичка — за свіжим вікном
    if len(recent) >= STABLE_MIN_DAYS and recent_weeks >= STABLE_MIN_WEEKS:
        if older:
            months = max(round(span / 30), 1)
            reason = (f"{len(recent)} покупок у {recent_weeks} різних тижнях за квартал, "
                      f"і так уже {months} міс.")
        else:
            reason = f"{len(recent)} покупок у {recent_weeks} різних тижнях за квартал"
        return Habit(STABLE, reason, len(days), weeks, span, coverage, since_last)

    # Свіжі покупки, злиплі в один епізод
    recent_span = (recent[-1] - recent[0]).days if len(recent) >= 2 else 0
    if len(recent) >= MIN_DAYS_FOR_REPEAT and recent_span <= EPISODE_WINDOW_DAYS:
        if older:
            return Habit(
                OCCASIONAL,
                f"брали й раніше, але рідко: {len(days)} разів за {max(span, 1)} дн.",
                len(days), weeks, span, coverage, since_last,
            )
        return Habit(
            EMERGING,
            f"{len(recent)} покупки за {max(recent_span, 1)} дн. — схоже на пробу, "
            "ритму ще не видно",
            len(days), weeks, span, coverage, since_last,
        )

    return Habit(
        OCCASIONAL, f"{len(days)} покупок за {max(span, 1)} дн. — надто рідко для ритму",
        len(days), weeks, span, coverage, since_last,
    )
