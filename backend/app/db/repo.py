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
            # 30 хвилин, а не 10: вхід відбувається в ЗОВНІШНЬОМУ браузері —
            # людина вводить телефон, чекає SMS, іноді відволікається.
            # Десяти хвилин вистачало на щасливий шлях і не вистачало на живий.
            "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        },
    )
    return state


# Скільки часу повторний колбек із тим самим state вважаємо тим самим
# входом. Браузер уміє повторювати редіректи, а людина — тиснути «назад».
REPLAY_WINDOW = timedelta(minutes=5)


async def consume_oauth_state(state: str) -> dict[str, Any] | None:
    """Забирає state під обмін на токени.

    Повертає рядок і вдруге, якщо колбек прилетів повторно протягом кількох
    хвилин: інакше оновлення сторінки або кнопка «назад» у браузері давали
    гостю «невалідний state» замість успішного входу.
    """
    row = await db().select_one("silpo_oauth_states", {"state": state})
    if not row:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
        return None

    consumed = row.get("consumed_at")
    if consumed:
        when = datetime.fromisoformat(consumed)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return row if datetime.now(UTC) - when <= REPLAY_WINDOW else None

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


async def find_user(handle: str) -> dict[str, Any] | None:
    """Гість за @username (без урахування регістру) або за Telegram ID."""
    handle = handle.lstrip("@").strip().lower()
    if handle.isdigit():
        return await get_user_by_telegram_id(int(handle))
    for row in await db().select("users", {}):
        if (row.get("username") or "").lower() == handle:
            return row
    return None


# --- Цілі та норми ----------------------------------------------------------
async def get_goal(user_id: str) -> dict[str, Any] | None:
    return await db().select_one("user_goals", {"user_id": user_id})


async def save_goal(user_id: str, values: dict[str, Any]) -> dict[str, Any]:
    return await db().upsert(
        "user_goals", {"user_id": user_id, "updated_at": _now(), **values}, on_conflict="user_id"
    )


# --- Налаштування агента ----------------------------------------------------
# Живуть у тому ж рядку user_goals: це та сама сутність «як агент має
# поводитися зі мною». Пишемо тільки передані поля, щоб не затерти норми.
PREF_FIELDS = (
    "mode", "price_tolerance", "restriction_strictness", "onboarded_at",
    "digest_sent_at",
)


async def get_prefs(user_id: str) -> dict[str, Any]:
    """Повертає ЛИШЕ наявні ключі.

    Це принципово: для price_tolerance значення None означає «без обмежень»,
    а відсутність ключа — «гість ще не налаштовував». Якби ми підставляли
    None для відсутніх, пропуск онбордингу читався б як «без обмежень».
    """
    row = await get_goal(user_id) or {}
    return {key: row[key] for key in PREF_FIELDS if key in row}


async def save_prefs(user_id: str, values: dict[str, Any]) -> dict[str, Any]:
    patch = {key: values[key] for key in PREF_FIELDS if key in values}
    if not patch:
        return await get_prefs(user_id)
    existing = await get_goal(user_id)
    if existing:
        await db().update("user_goals", {"user_id": user_id}, {**patch, "updated_at": _now()})
    else:
        # Рядка ще немає: створюємо мінімальний, не вигадуючи харчових норм.
        # Дефолти дублюють DEFAULT колонок із міграції 0004, щоб in-memory
        # режим поводився так само, як база.
        await db().upsert(
            "user_goals",
            {
                "user_id": user_id, "goal": "health", "mode": "auto",
                "price_tolerance": 0.05, "restriction_strictness": {},
                "updated_at": _now(), **patch,
            },
            on_conflict="user_id",
        )
    return await get_prefs(user_id)


# --- Кошик застосунку ---------------------------------------------------------
# Товар з будь-якого екрана лягає сюди. У кошик Сільпо пишемо один раз — на
# «Оформити», щоб гість міг збирати набір і передумувати без наслідків.
async def cart_items(user_id: str) -> list[dict[str, Any]]:
    return await db().select("app_cart", {"user_id": user_id}, order="added_at", desc=False)


async def cart_add(user_id: str, item: dict[str, Any]) -> dict[str, Any]:
    """Повторне додавання того самого товару збільшує кількість, а не дублює рядок."""
    existing = await db().select_one(
        "app_cart", {"user_id": user_id, "product_id": item["product_id"]}
    )
    if existing:
        quantity = int(existing.get("quantity") or 1) + int(item.get("quantity") or 1)
        await db().update(
            "app_cart", {"id": existing["id"]}, {"quantity": quantity}
        )
        return {**existing, "quantity": quantity}
    return await db().insert("app_cart", {
        "user_id": user_id,
        "product_id": item["product_id"],
        "slug": item.get("slug"),
        "name": item.get("name"),
        "image": item.get("image"),
        "price": item.get("price"),
        "quantity": max(int(item.get("quantity") or 1), 1),
        "source": item.get("source"),
        "added_at": _now(),
    })


async def cart_set_quantity(user_id: str, item_id: str, quantity: int) -> None:
    if quantity <= 0:
        await db().delete("app_cart", {"id": item_id, "user_id": user_id})
        return
    await db().update("app_cart", {"id": item_id, "user_id": user_id}, {"quantity": quantity})


async def cart_remove(user_id: str, item_id: str) -> None:
    await db().delete("app_cart", {"id": item_id, "user_id": user_id})


async def cart_clear(user_id: str) -> None:
    await db().delete("app_cart", {"user_id": user_id})


# --- Цикли покупок і стеження за цінами ---------------------------------------
async def cycles_for(user_id: str) -> dict[str, dict[str, Any]]:
    rows = await db().select("product_cycles", {"user_id": user_id})
    return {r["slug"]: r for r in rows}


async def save_cycle(user_id: str, slug: str, values: dict[str, Any]) -> dict[str, Any]:
    return await db().upsert(
        "product_cycles",
        {"user_id": user_id, "slug": slug, "updated_at": _now(), **values},
        on_conflict="user_id,slug",
    )


async def price_snapshot(user_id: str) -> dict[str, dict[str, Any]]:
    rows = await db().select("price_watch", {"user_id": user_id})
    return {r["slug"]: r for r in rows}


async def save_price_snapshot(user_id: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        await db().upsert(
            "price_watch",
            {"user_id": user_id, "seen_at": _now(), **row},
            on_conflict="user_id,slug",
        )


async def users_with_tokens() -> list[dict[str, Any]]:
    """Кому взагалі є сенс слати дайджест."""
    rows = await db().select("silpo_oauth_tokens", {})
    return [{"user_id": r["user_id"]} for r in rows if r.get("user_id")]


# --- Метрика рішень -----------------------------------------------------------
async def open_decisions(user_id: str) -> list[dict[str, Any]]:
    """Пропозиції, щодо яких гість ще не вирішив."""
    rows = await db().select("decisions", {"user_id": user_id})
    return [r for r in rows if r.get("accepted") is None]


async def record_decision(user_id: str, values: dict[str, Any]) -> dict[str, Any]:
    return await db().insert("decisions", {"user_id": user_id, "shown_at": _now(), **values})


async def get_decision(user_id: str, decision_id: str) -> dict[str, Any] | None:
    return await db().select_one("decisions", {"id": decision_id, "user_id": user_id})


async def decide(decision_id: str, accepted: bool) -> None:
    await db().update(
        "decisions", {"id": decision_id}, {"accepted": accepted, "decided_at": _now()}
    )


async def all_decisions(user_id: str) -> list[dict[str, Any]]:
    return await db().select("decisions", {"user_id": user_id}, order="shown_at", desc=True)


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
