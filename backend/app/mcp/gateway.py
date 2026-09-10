"""Єдина точка входу до MCP: реальна сесія або фікстури (DEMO_MODE).

Сервіси працюють тільки з цим інтерфейсом і не знають про транспорт.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from app.config import get_settings
from app.mcp import fixtures, logbus
from app.mcp.client import McpNotConnected, McpToolForbidden, mcp_session  # noqa: F401 (реекспорт)

log = logging.getLogger("mcp")


class DemoGateway:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.demo = True

    async def list_tools(self) -> list[dict[str, Any]]:
        tools = await fixtures.list_tools()
        await logbus.record(
            user_id=self.user_id, tool_name="tools/list",
            request={}, response={"count": len(tools), "names": [t["name"] for t in tools]},
        )
        return tools

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        started = time.monotonic()
        data = await fixtures.call(name, arguments or {})
        await logbus.record(
            user_id=self.user_id, tool_name=name, request=arguments or {}, response=data,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return data


class ResilientSilpo:
    """Обгортка, яка переживає обрив MCP-з'єднання.

    Побудова плану — це 30+ викликів tools поспіль протягом хвилини. Streamable
    HTTP-сесія за цей час може обірватись (httpx2.ReadError), і тоді падала вся
    задача, а клієнт бачив нескінченне «читаю чеки».

    Тепер обрив транспорту не фатальний: сесія відкривається наново, і виклик
    повторюється. Для сервісів вище нічого не змінюється — інтерфейс той самий.
    """

    TRANSPORT_ERRORS = ("ReadError", "WriteError", "ConnectError", "RemoteProtocolError",
                        "ClosedResourceError", "BrokenResourceError", "ConnectionResetError")
    MAX_RECONNECTS = 3

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.demo = False
        self._stack: AsyncExitStack | None = None
        self._api = None

    async def _open(self) -> None:
        self._stack = AsyncExitStack()
        self._api = await self._stack.enter_async_context(mcp_session(self.user_id))

    async def _close(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:  # noqa: BLE001 — з'єднання й так мертве
                pass
        self._stack = None
        self._api = None

    async def __aenter__(self) -> "ResilientSilpo":
        await self._open()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._close()

    @classmethod
    def _is_transport_error(cls, exc: BaseException) -> bool:
        seen: list[BaseException] = [exc]
        while seen:
            current = seen.pop()
            if type(current).__name__ in cls.TRANSPORT_ERRORS:
                return True
            if isinstance(current, BaseExceptionGroup):
                seen.extend(current.exceptions)
            if current.__cause__:
                seen.append(current.__cause__)
        return False

    async def list_tools(self):
        return await self._api.list_tools()

    async def call(self, name: str, arguments=None):
        for attempt in range(self.MAX_RECONNECTS):
            try:
                return await self._api.call(name, arguments)
            except Exception as exc:  # noqa: BLE001
                if attempt == self.MAX_RECONNECTS - 1 or not self._is_transport_error(exc):
                    raise
                log.warning(
                    "MCP-зʼєднання обірвалось на %s — перепідключаюсь (спроба %d)",
                    name, attempt + 1,
                )
                await self._close()
                await asyncio.sleep(1.5 * (attempt + 1))
                await self._open()
        raise RuntimeError("MCP недоступний після кількох спроб перепідключення")


@asynccontextmanager
async def silpo(user_id: str):
    if get_settings().demo_mode:
        yield DemoGateway(user_id)
        return
    async with ResilientSilpo(user_id) as api:
        yield api
