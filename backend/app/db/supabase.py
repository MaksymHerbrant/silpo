"""Тонкий клієнт до Supabase PostgREST (service_role key, тільки бекенд).

Свідомо без supabase-py: нам потрібні лише CRUD-запити, а httpx уже в залежностях.
Якщо SUPABASE_URL не заданий — вмикається in-memory фолбек, щоб застосунок
піднімався локально без хмари (зручно для розробки UI).
"""
from __future__ import annotations

import itertools
import threading
from typing import Any

import httpx

from app.config import get_settings


class MemoryDB:
    """Мінімальний in-memory замінник PostgREST для локальної розробки."""

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._seq = itertools.count(1)
        self._lock = threading.Lock()

    def _t(self, table: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(table, [])

    @staticmethod
    def _match(row: dict[str, Any], filters: dict[str, Any]) -> bool:
        return all(row.get(k) == v for k, v in filters.items())

    def select(self, table, filters=None, order=None, desc=True, limit=None):
        rows = [r for r in self._t(table) if self._match(r, filters or {})]
        if order:
            rows.sort(key=lambda r: (r.get(order) is None, r.get(order)), reverse=desc)
        return rows[:limit] if limit else rows

    def insert(self, table, values):
        with self._lock:
            row = dict(values)
            row.setdefault("id", str(next(self._seq)))
            self._t(table).append(row)
            return row

    def upsert(self, table, values, on_conflict):
        keys = [k.strip() for k in on_conflict.split(",")]
        with self._lock:
            for row in self._t(table):
                if all(row.get(k) == values.get(k) for k in keys):
                    row.update(values)
                    return row
        return self.insert(table, values)

    def update(self, table, filters, values):
        out = []
        with self._lock:
            for row in self._t(table):
                if self._match(row, filters):
                    row.update(values)
                    out.append(row)
        return out

    def delete(self, table, filters):
        with self._lock:
            keep = [r for r in self._t(table) if not self._match(r, filters)]
            removed = len(self._t(table)) - len(keep)
            self._tables[table] = keep
        return removed


class SupabaseClient:
    def __init__(self) -> None:
        s = get_settings()
        self.url = s.supabase_url.rstrip("/")
        self.key = s.supabase_service_role_key
        self.enabled = bool(self.url and self.key)
        self.memory = MemoryDB()
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=f"{self.url}/rest/v1",
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                },
                timeout=20.0,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- CRUD ---------------------------------------------------------------
    async def select(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        desc: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return self.memory.select(table, filters, order, desc, limit)
        params: dict[str, str] = {"select": "*"}
        for k, v in (filters or {}).items():
            params[k] = f"eq.{v}"
        if order:
            params["order"] = f"{order}.{'desc' if desc else 'asc'}"
        if limit:
            params["limit"] = str(limit)
        r = await self._http().get(f"/{table}", params=params)
        r.raise_for_status()
        return r.json()

    async def select_one(self, table: str, filters: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self.select(table, filters, limit=1)
        return rows[0] if rows else None

    async def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return self.memory.insert(table, values)
        r = await self._http().post(
            f"/{table}", json=values, headers={"Prefer": "return=representation"}
        )
        r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data, list) and data else values

    async def upsert(self, table: str, values: dict[str, Any], on_conflict: str) -> dict[str, Any]:
        if not self.enabled:
            return self.memory.upsert(table, values, on_conflict)
        r = await self._http().post(
            f"/{table}",
            json=values,
            params={"on_conflict": on_conflict},
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data, list) and data else values

    async def update(
        self, table: str, filters: dict[str, Any], values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return self.memory.update(table, filters, values)
        params = {k: f"eq.{v}" for k, v in filters.items()}
        r = await self._http().patch(
            f"/{table}", params=params, json=values, headers={"Prefer": "return=representation"}
        )
        r.raise_for_status()
        return r.json()

    async def delete(self, table: str, filters: dict[str, Any]) -> None:
        if not self.enabled:
            self.memory.delete(table, filters)
            return
        params = {k: f"eq.{v}" for k, v in filters.items()}
        r = await self._http().delete(f"/{table}", params=params)
        r.raise_for_status()


_db: SupabaseClient | None = None


def db() -> SupabaseClient:
    global _db
    if _db is None:
        _db = SupabaseClient()
    return _db
