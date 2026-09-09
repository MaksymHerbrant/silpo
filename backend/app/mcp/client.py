"""Клієнт офіційного MCP Сільпо (Streamable HTTP, Python MCP SDK).

Одна сесія на один аналіз: відкриваємо ClientSession, робимо N викликів
tools/call, закриваємо. Всі виклики йдуть через throttle + backoff і пишуться
в logbus (для /debug/mcp-log).

Обробка помилок згідно з вимогами:
  401 -> refresh токена і один повтор
  403 -> немає доступу до tool (не ретраїмо, повідомляємо явно)
  429 -> експоненційний backoff
"""
from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import (
    create_mcp_http_client,
    streamable_http_client,
)

from app.config import get_settings
from app.mcp import logbus, oauth
from app.mcp.ratelimit import RateLimitError, with_backoff


class McpNotConnected(RuntimeError):
    """Користувач ще не під'єднав акаунт Сільпо."""


class McpToolForbidden(RuntimeError):
    """403 — у гостя немає доступу до цього tool."""


def _classify(exc: Exception) -> Exception:
    text = str(exc)
    if "429" in text or "Too Many Requests" in text:
        return RateLimitError()
    if "403" in text or "Forbidden" in text:
        return McpToolForbidden(text)
    return exc


def _content_to_data(result: Any) -> Any:
    """MCP повертає список content-блоків. Дістаємо structured/JSON, якщо є."""
    structured = getattr(result, "structuredContent", None)
    if structured:
        return structured
    out: list[Any] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None:
            out.append({"type": getattr(block, "type", "unknown")})
            continue
        try:
            out.append(json.loads(text))
        except (TypeError, ValueError):
            out.append(text)
    if not out:
        return None
    return out[0] if len(out) == 1 else out


class SilpoMCP:
    def __init__(self, user_id: str, session: ClientSession, access_token: str) -> None:
        self.user_id = user_id
        self._session = session
        self._access_token = access_token
        self.tools_cache: list[dict[str, Any]] | None = None

    async def list_tools(self) -> list[dict[str, Any]]:
        started = time.monotonic()
        result = await self._session.list_tools()
        tools = [
            {"name": t.name, "description": t.description, "input_schema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)}
            for t in result.tools
        ]
        self.tools_cache = tools
        await logbus.record(
            user_id=self.user_id,
            tool_name="tools/list",
            request={},
            response={"count": len(tools), "names": [t["name"] for t in tools]},
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return tools

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        arguments = arguments or {}

        async def _once() -> Any:
            started = time.monotonic()
            try:
                result = await self._session.call_tool(name, arguments)
            except Exception as exc:  # noqa: BLE001 — класифікуємо і прокидаємо далі
                await logbus.record(
                    user_id=self.user_id,
                    tool_name=name,
                    request=arguments,
                    response={"error": str(exc)[:800]},
                    status="error",
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
                raise _classify(exc) from exc

            data = _content_to_data(result)
            if getattr(result, "isError", False):
                await logbus.record(
                    user_id=self.user_id,
                    tool_name=name,
                    request=arguments,
                    response=data,
                    status="error",
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
                raise _classify(RuntimeError(json.dumps(data, ensure_ascii=False)[:500]))

            await logbus.record(
                user_id=self.user_id,
                tool_name=name,
                request=arguments,
                response=data,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return data

        return await with_backoff(_once, user_id=self.user_id)


@asynccontextmanager
async def mcp_session(user_id: str):
    """Відкриває MCP-сесію під токен користувача. На 401 — один refresh і повтор."""
    settings = get_settings()
    token = await oauth.get_valid_access_token(user_id)
    if not token:
        raise McpNotConnected("Акаунт Сільпо не під'єднано")

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            http_client = create_mcp_http_client(
                headers={"Authorization": f"Bearer {token}"}
            )
            async with http_client, streamable_http_client(
                settings.silpo_mcp_url, http_client=http_client
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield SilpoMCP(user_id, session, token)
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            unauthorized = "401" in str(exc) or "Unauthorized" in str(exc)
            if attempt == 0 and unauthorized:
                refreshed = await oauth.force_refresh(user_id)
                if refreshed:
                    token = refreshed
                    continue
                raise McpNotConnected("Токен Сільпо протух, потрібне повторне під'єднання") from exc
            raise
    if last_error:
        raise last_error
