"""Демо-панель: сирі JSON-RPC виклики MCP за поточну сесію.

Обовʼязковий пункт вимог хакатону — видимий доказ реального виклику tool.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.mcp import logbus
from app.mcp.gateway import silpo
from app.security.session import current_user_id

router = APIRouter(tags=["debug"])


@router.get("/debug/mcp-log")
async def mcp_log(limit: int = 50, user_id: str = Depends(current_user_id)) -> dict:
    return {
        "endpoint": get_settings().silpo_mcp_url,
        "demo_mode": get_settings().demo_mode,
        "entries": logbus.tail(user_id, limit),
    }


@router.post("/debug/mcp-log/clear")
async def clear_log(user_id: str = Depends(current_user_id)) -> dict:
    logbus.clear()
    return {"cleared": True}


@router.get("/debug/tools")
async def list_tools(user_id: str = Depends(current_user_id)) -> dict:
    """tools/list — показуємо журі повний перелік доступних tools."""
    async with silpo(user_id) as api:
        tools = await api.list_tools()
    return {"count": len(tools), "tools": tools}
