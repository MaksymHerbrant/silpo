"""Черга з мінімальним інтервалом + експоненційний backoff на 429.

Кошик на 20+ товарів => 20+ послідовних silpo_get_product_details.
Без цього ми гарантовано впираємось у per-user rate limit MCP.
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict

from app.config import get_settings


class RateLimitError(Exception):
    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("429 Too Many Requests від MCP")
        self.retry_after = retry_after


class UserThrottle:
    """Обмежує НАВАНТАЖЕННЯ, а не паралельність як таку.

    Раніше тут був лок: усі виклики одного гостя шикувались у чергу по одному.
    Це надійно, але дорого — 43 виклики побудови перетворювались на 29 секунд
    очікування, з яких третина була нашою ж паузою в 250 мс.

    Тепер два незалежні запобіжники:
      * семафор — скільки викликів одночасно в польоті;
      * мінімальний інтервал МІЖ СТАРТАМИ — щоб не бити чергою в MCP.

    Захист від 429 лишається (backoff нижче), але звичайний шлях швидший.
    """

    _semaphores: dict[str, asyncio.Semaphore] = {}
    _gates: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    _last_start: dict[str, float] = defaultdict(float)

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    @classmethod
    def _semaphore(cls, user_id: str) -> asyncio.Semaphore:
        limit = max(1, get_settings().mcp_concurrency)
        existing = cls._semaphores.get(user_id)
        if existing is None or getattr(existing, "_nk_limit", None) != limit:
            existing = asyncio.Semaphore(limit)
            existing._nk_limit = limit  # noqa: SLF001 — щоб підхопити зміну налаштування
            cls._semaphores[user_id] = existing
        return existing

    async def __aenter__(self) -> "UserThrottle":
        await self._semaphore(self.user_id).acquire()
        gap = get_settings().mcp_min_interval_ms / 1000
        async with self._gates[self.user_id]:
            delta = time.monotonic() - self._last_start[self.user_id]
            if delta < gap:
                await asyncio.sleep(gap - delta)
            self._last_start[self.user_id] = time.monotonic()
        return self

    async def __aexit__(self, *exc) -> None:
        self._semaphore(self.user_id).release()


async def with_backoff(coro_factory, *, user_id: str):
    """Виконує coro_factory() з ретраями на 429 (експоненційний backoff + jitter)."""
    s = get_settings()
    attempt = 0
    while True:
        try:
            async with UserThrottle(user_id):
                return await coro_factory()
        except RateLimitError as exc:
            attempt += 1
            if attempt > s.mcp_max_retries:
                raise
            delay = exc.retry_after or (s.mcp_backoff_base_ms / 1000) * (2 ** (attempt - 1))
            await asyncio.sleep(min(delay, 30) + random.uniform(0, 0.25))
