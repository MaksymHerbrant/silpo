"""Кільцевий буфер JSON-RPC викликів MCP — джерело для GET /debug/mcp-log.

Хакатон вимагає видимого доказу реального виклику tool. Тут ми пишемо
запит/відповідь кожного tools/call і віддаємо їх у демо-панель фронтенду
(+ дублюємо в Supabase.mcp_call_log, якщо БД під'єднана).
"""
from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import UTC, datetime
from typing import Any

MAX_ENTRIES = 300
_entries: deque[dict[str, Any]] = deque(maxlen=MAX_ENTRIES)
_counter = 0
_lock = asyncio.Lock()


def _truncate(obj: Any, limit: int = 4000) -> Any:
    """Обрізаємо величезні відповіді, щоб демо-панель не лягла."""
    try:
        raw = json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        raw = str(obj)
    if len(raw) <= limit:
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw
    return {"_truncated": True, "_size": len(raw), "preview": raw[:limit]}


async def record(
    *,
    user_id: str | None,
    tool_name: str,
    request: Any,
    response: Any = None,
    status: str = "ok",
    duration_ms: int = 0,
    http_status: int | None = None,
) -> dict[str, Any]:
    global _counter
    async with _lock:
        _counter += 1
        seq = _counter
    entry = {
        "seq": seq,
        "user_id": user_id,
        "ts": datetime.now(UTC).isoformat(),
        "tool": tool_name,
        "status": status,
        "duration_ms": duration_ms,
        "http_status": http_status,
        # Показуємо саме JSON-RPC-подібний конверт, який іде в MCP
        "jsonrpc_request": {
            "jsonrpc": "2.0",
            "id": seq,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": _truncate(request, 2000)},
        },
        "jsonrpc_response": _truncate(response),
    }
    _entries.append(entry)

    # Дзеркалимо в БД, але не валимо основний флоу через помилку логування.
    try:
        from app.db.supabase import db

        await db().insert(
            "mcp_call_log",
            {
                "user_id": user_id,
                "tool_name": tool_name,
                "request": entry["jsonrpc_request"],
                "response": entry["jsonrpc_response"],
                "status": status,
                "http_status": http_status,
                "duration_ms": duration_ms,
                "created_at": entry["ts"],
            },
        )
    except Exception:  # noqa: BLE001 — лог не критичний для сценарію
        pass
    return entry


def tail(user_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    items = [e for e in _entries if user_id is None or e["user_id"] == user_id]
    return list(reversed(items[-limit:]))


def clear() -> None:
    _entries.clear()
