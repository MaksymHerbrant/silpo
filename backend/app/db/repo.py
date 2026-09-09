"""Доменні операції над таблицями Supabase."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.supabase import db
from app.security.crypto import decrypt, encrypt


def _now() -> str:
    return datetime.now(UTC).isoformat()


# --- users ------------------------------------------------------------------
async def upsert_user(telegram_id: int, **profile: Any) -> dict[str, Any]:
    existing = await db().select_one("users", {"telegram_id": telegram_id})
    if existing:
        await db().update("users", {"id": existing["id"]}, {"last_seen_at": _now(), **profile})
        return {**existing, **profile}
    return await db().insert(
        "users", {"telegram_id": telegram_id, "created_at": _now(), "last_seen_at": _now(), **profile}
    )


# --- OAuth ------------------------------------------------------------------
async def save_oauth_state(user_id: str, code_verifier: str, redirect_uri: str) -> str:
    state = secrets.token_urlsafe(32)
    await db().insert(
        "silpo_oauth_states",
        {
            "state": state,
            "user_id": user_id,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "created_at": _now(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        },
    )
    return state


async def consume_oauth_state(state: str) -> dict[str, Any] | None:
    row = await db().select_one("silpo_oauth_states", {"state": state})
    if not row or row.get("consumed_at"):
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
        return None
    await db().update("silpo_oauth_states", {"state": state}, {"consumed_at": _now()})
    return row


async def save_tokens(
    user_id: str,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
    scope: str | None = None,
    token_type: str = "Bearer",
) -> None:
    await db().upsert(
        "silpo_oauth_tokens",
        {
            "user_id": user_id,
            "access_token": encrypt(access_token),
            "refresh_token": encrypt(refresh_token),
            "token_type": token_type,
            "scope": scope,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=max(int(expires_in), 60))).isoformat(),
            "updated_at": _now(),
        },
        on_conflict="user_id",
    )


async def get_tokens(user_id: str) -> dict[str, Any] | None:
    """Повертає розшифровані токени. Наліво (у фронтенд) НЕ віддавати."""
    row = await db().select_one("silpo_oauth_tokens", {"user_id": user_id})
    if not row:
        return None
    return {
        "access_token": decrypt(row["access_token"]),
        "refresh_token": decrypt(row.get("refresh_token")),
        "expires_at": datetime.fromisoformat(row["expires_at"]),
        "token_type": row.get("token_type", "Bearer"),
    }


async def drop_tokens(user_id: str) -> None:
    await db().delete("silpo_oauth_tokens", {"user_id": user_id})


# --- startapp deep-link токени ---------------------------------------------
async def issue_startapp_token(user_id: str) -> str:
    token = secrets.token_urlsafe(24)
    await db().insert(
        "startapp_tokens",
        {
            "token": token,
            "user_id": user_id,
            "created_at": _now(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
        },
    )
    return token


async def consume_startapp_token(token: str) -> str | None:
    row = await db().select_one("startapp_tokens", {"token": token})
    if not row or row.get("consumed_at"):
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
        return None
    await db().update("startapp_tokens", {"token": token}, {"consumed_at": _now()})
    return row["user_id"]


# --- аналітика --------------------------------------------------------------
async def cache_cart_analysis(user_id: str, cart_id: str, items: list[dict], score: int | None) -> None:
    await db().upsert(
        "cart_analysis_cache",
        {
            "user_id": user_id,
            "cart_id": cart_id,
            "computed_at": _now(),
            "items_json": items,
            "health_score": score,
        },
        on_conflict="user_id,cart_id",
    )


async def get_cached_analysis(user_id: str, cart_id: str) -> dict[str, Any] | None:
    return await db().select_one("cart_analysis_cache", {"user_id": user_id, "cart_id": cart_id})


async def upsert_weekly_snapshot(user_id: str, snapshot: dict[str, Any]) -> None:
    await db().upsert(
        "weekly_snapshots", {"user_id": user_id, **snapshot}, on_conflict="user_id,week_start_date"
    )


async def list_weekly_snapshots(user_id: str, limit: int = 12) -> list[dict[str, Any]]:
    return await db().select(
        "weekly_snapshots", {"user_id": user_id}, order="week_start_date", desc=True, limit=limit
    )


async def save_swap_suggestions(user_id: str, suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saved = []
    for s in suggestions:
        saved.append(await db().insert("swap_suggestions", {"user_id": user_id, "created_at": _now(), **s}))
    return saved


async def list_swap_suggestions(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    return await db().select("swap_suggestions", {"user_id": user_id}, order="created_at", limit=limit)


async def get_swap(user_id: str, swap_id: str) -> dict[str, Any] | None:
    return await db().select_one("swap_suggestions", {"id": swap_id, "user_id": user_id})


async def mark_swap(swap_id: str, accepted: bool) -> None:
    await db().update("swap_suggestions", {"id": swap_id}, {"accepted": accepted, "decided_at": _now()})


async def swap_acceptance_stats(user_id: str) -> dict[str, Any]:
    rows = await db().select("swap_suggestions", {"user_id": user_id})
    decided = [r for r in rows if r.get("accepted") is not None]
    accepted = [r for r in decided if r["accepted"]]
    return {
        "total": len(rows),
        "decided": len(decided),
        "accepted": len(accepted),
        "acceptance_rate": round(len(accepted) / len(decided) * 100, 1) if decided else None,
    }


# --- Dynamic Client Registration -------------------------------------------
async def get_oauth_client(issuer: str, redirect_uri: str) -> dict[str, Any] | None:
    row = await db().select_one("oauth_clients", {"issuer": issuer, "redirect_uri": redirect_uri})
    if not row:
        return None
    return {
        "client_id": row["client_id"],
        "client_secret": decrypt(row.get("client_secret")),
        "auth_method": row.get("auth_method", "none"),
    }


async def save_oauth_client(
    issuer: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str | None,
    auth_method: str,
    raw: dict[str, Any],
) -> None:
    await db().upsert(
        "oauth_clients",
        {
            "issuer": issuer,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": encrypt(client_secret),
            "auth_method": auth_method,
            "raw_response": raw,
            "created_at": _now(),
        },
        on_conflict="issuer,redirect_uri",
    )


async def get_user(user_id: str) -> dict[str, Any] | None:
    return await db().select_one("users", {"id": user_id})


async def get_user_by_telegram_id(telegram_id: int) -> dict[str, Any] | None:
    return await db().select_one("users", {"telegram_id": telegram_id})


# --- Цілі та норми ----------------------------------------------------------
async def get_goal(user_id: str) -> dict[str, Any] | None:
    return await db().select_one("user_goals", {"user_id": user_id})


async def save_goal(user_id: str, values: dict[str, Any]) -> dict[str, Any]:
    return await db().upsert(
        "user_goals", {"user_id": user_id, "updated_at": _now(), **values}, on_conflict="user_id"
    )


async def save_plan(user_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    return await db().insert("basket_plans", {
        "user_id": user_id,
        "created_at": _now(),
        "budget": plan.get("budget"),
        "total_price": plan.get("total_price"),
        "items_json": plan.get("items"),
        "coverage": plan.get("coverage_pct"),
    })


async def get_plan(user_id: str, plan_id: str) -> dict[str, Any] | None:
    return await db().select_one("basket_plans", {"id": plan_id, "user_id": user_id})


async def mark_plan_applied(plan_id: str) -> None:
    await db().update("basket_plans", {"id": plan_id}, {"applied": True, "applied_at": _now()})
