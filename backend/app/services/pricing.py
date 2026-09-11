"""Ціновий поріг гостя — єдине місце, де живе рішення «наскільки дорожче можна».

Опитування 21 респондента дало однозначну картину: ціна — критерій вибору №1
(62%), а готовність переплачувати низька (30% — до 5%, 25% — 5–10%, 5% — не
готові взагалі). Тому поріг застосовується ПЕРШИМ, ще до будь-яких міркувань
про користь: кандидат, що вийшов за поріг, для решти логіки просто не існує.

Користь для здоров'я не зникає — вона вирішує ВСЕРЕДИНІ цінового коридору.
Дві заміни, що економлять 12 ₴ і 14 ₴, потрапляють в одну цінову смугу
(`SAVING_BAND`), і серед них перемагає здоровіша. Заміна на 40 ₴ дешевша за
заміну на 12 ₴ — і жодна дієтологія цього не переб'є.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Sequence, TypeVar

# Дефолт із опитування: найбільша група готова переплатити до 5%
DEFAULT_TOLERANCE = 0.05
# Навіть «без обмежень» не означає «пропонуй утричі дорожче»
SANITY_CAP = 2.0
# Крок 5 ₴: усередині однієї смуги ціни вважаються рівними
SAVING_BAND = 5.0
# Копійчаний допуск, щоб 105.00 не випадало з порогу 105.0 через float
EPSILON = 0.01

# Варіанти для екрана налаштувань. value=None означає «без обмежень».
OPTIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "strict", "value": 0.0, "label": "Тільки не дорожче",
        "hint": "Показуємо лише дешевші або за тією ж ціною",
    },
    {
        "key": "low", "value": 0.05, "label": "До 5%",
        "hint": "Найчастіший вибір",
    },
    {
        "key": "medium", "value": 0.10, "label": "До 10%",
        "hint": "Більше варіантів для заміни",
    },
    {
        "key": "any", "value": None, "label": "Без обмежень",
        "hint": "Ціна не фільтрує пропозиції",
    },
)

_UNLIMITED_WORDS = {"any", "none", "unlimited", "без обмежень"}


def normalize(value: Any) -> float | None:
    """Приводить що завгодно до частки. None = «без обмежень».

    Приймає і 0.05, і 5, і "5%", і "any" — бо це значення приходить і з бази,
    і з JSON фронтенду, і з дефолтів.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower().replace("%", "").replace(",", ".")
        if not text:
            return DEFAULT_TOLERANCE
        if text in _UNLIMITED_WORDS:
            return None
        value = text
    try:
        num = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TOLERANCE
    if num > 1:                       # прийшло «5» замість «0.05»
        num /= 100
    return min(max(num, 0.0), SANITY_CAP - 1.0)


def max_ratio(tolerance: Any) -> float:
    """У скільки разів максимум може бути дорожчою альтернатива."""
    value = normalize(tolerance)
    return SANITY_CAP if value is None else 1.0 + value


def cap_for(price: float | None, tolerance: Any) -> float | None:
    """Гранична ціна кандидата. None — якщо порівнювати нема з чим."""
    if not price:
        return None
    return price * max_ratio(tolerance)


def is_within(original_price: float | None, candidate_price: float | None, tolerance: Any) -> bool:
    """Чи вкладається кандидат у поріг гостя.

    Якщо ціни немає з якогось боку — не відсікаємо: краще показати позицію
    без цінового судження, ніж мовчки її загубити.
    """
    cap = cap_for(original_price, tolerance)
    if cap is None or not candidate_price:
        return True
    return candidate_price <= cap + EPSILON


P = TypeVar("P", bound=Sequence)


def split(
    original_price: float | None,
    candidates: Iterable[P],
    tolerance: Any,
) -> tuple[list[P], list[P]]:
    """Ділить пари (товар, економія) на «в межах порогу» і «поза ним».

    `over` не викидається: воно живе під «показати ще варіанти» і ніколи не
    підставляється саме собою.
    """
    within: list[P] = []
    over: list[P] = []
    for pair in candidates:
        candidate = pair[0]
        price = getattr(candidate, "price", None)
        (within if is_within(original_price, price, tolerance) else over).append(pair)
    return within, over


def _band(saving: float | None) -> int:
    return int(round((saving or 0) / SAVING_BAND))


def rank(pairs: Iterable[P], health_of: Callable[[Any], int] | None = None) -> list[P]:
    """Сортує кандидатів: ціна первинна, користь вирішує лише в межах смуги."""
    health = health_of or (lambda _candidate: 0)

    def key(pair: P) -> tuple[int, int, float]:
        candidate, saving = pair[0], pair[1]
        return (-_band(saving), -(health(candidate) or 0), getattr(candidate, "price", 0) or 0)

    return sorted(pairs, key=key)


def combine(rule_ratio: float, tolerance: Any) -> float:
    """Правило заміни й поріг гостя обмежують ціну разом — перемагає суворіший."""
    return min(rule_ratio, max_ratio(tolerance))


def describe(tolerance: Any) -> str:
    """Людський підпис порогу для інтерфейсу."""
    value = normalize(tolerance)
    if value is None:
        return "без обмежень"
    if value <= 0:
        return "тільки не дорожче"
    return f"до {round(value * 100)}%"


def option_key(tolerance: Any) -> str:
    """Який із варіантів налаштувань зараз активний."""
    value = normalize(tolerance)
    for option in OPTIONS:
        if option["value"] is None and value is None:
            return str(option["key"])
        if option["value"] is not None and value is not None:
            if abs(float(option["value"]) - value) < 0.001:
                return str(option["key"])
    return "custom"
