"""Єдина точка входу до MCP: реальна сесія або фікстури (DEMO_MODE).

Сервіси працюють тільки з цим інтерфейсом і не знають про транспорт.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from app.config import get_settings
from app.mcp import fixtures, logbus
from app.mcp.client import McpNotConnected, McpToolForbidden, mcp_session  # noqa: F401 (реекспорт)


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


@asynccontextmanager
async def silpo(user_id: str):
    if get_settings().demo_mode:
        yield DemoGateway(user_id)
        return
    async with mcp_session(user_id) as api:
        api.demo = False
        yield api
