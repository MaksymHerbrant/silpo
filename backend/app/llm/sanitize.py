"""Захист від вигаданих чисел.

Модель добре формулює й добре міркує про товари. Але будь-яке число, що
потрапляє на екран, має бути порахованим НАМИ. Тому кожну цифру з відповіді
звіряємо зі списком чисел, які справді є у фактах.

Це не декларація в промпті, а фільтр: знайшлось чуже число — речення
відкидається цілком і підставляється детермінований запасний варіант.
"""
from __future__ import annotations

import re
from typing import Any

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
# Дрібні числа трапляються в звичайній мові («один», «2 рази») і не є
# твердженням про дані — але їх усе одно перевіряємо, просто вони майже
# завжди присутні у фактах.
ALWAYS_ALLOWED = {"0", "1", "2", "3", "4", "5", "6", "7", "10", "100"}


def _norm(value: Any) -> str:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def walk_numbers(payload: Any) -> list[float]:
    """Усі числа з фактів, включно з тими, що всередині рядків."""
    found: list[float] = []
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
        elif isinstance(node, bool):
            continue
        elif isinstance(node, (int, float)):
            found.append(float(node))
        elif isinstance(node, str):
            found.extend(float(m.replace(",", ".")) for m in NUMBER.findall(node))
    return found


def allowed_numbers(payload: Any) -> set[str]:
    """Числа з фактів плюс їх природні округлення."""
    out = set(ALWAYS_ALLOWED)
    for value in walk_numbers(payload):
        out.add(_norm(value))
        out.add(_norm(round(value)))
        out.add(_norm(round(value, 1)))
    return out


def check(text: str, allowed: set[str]) -> str | None:
    """Повертає перше чуже число або None, якщо всі числа з фактів."""
    for token in NUMBER.findall(text or ""):
        if _norm(token) not in allowed:
            return token
    return None


def sanitize(text: str, payload: Any, fallback: str = "") -> str:
    """Текст без вигаданих чисел. Інакше — запасний детермінований варіант."""
    allowed = allowed_numbers(payload)
    return fallback if check(text, allowed) else text
