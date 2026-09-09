"""OAuth 2.1 + PKCE + Dynamic Client Registration до MCP Сільпо.

Сільпо не видає client_id заздалегідь: за RFC 7591 клієнт реєструє себе сам
(POST /register), і вже отриманий client_id використовує в /authorize та /token.
Реєстрація прив'язана до redirect_uri, тому кешується в БД і перевикористовується.

Особливість Telegram WebView: popup-вікна для стороннього OAuth там працюють
нестабільно. Тому флоу такий:

  Mini App                Backend                     auth.silpo.ua
     |  POST /auth/silpo/start  |                            |
     |------------------------->|  генерує PKCE + state      |
     |<-- authorize_url --------|                            |
     |  Telegram.WebApp.openLink(authorize_url)  --> ЗОВНІШНІЙ БРАУЗЕР
     |                          |                            |
     |                          |<-- GET /auth/silpo/callback?code=...&state=...
     |                          |  обмін code -> token, шифрує, кладе в Supabase
     |                          |  редірект на t.me/<bot>/<app>?startapp=<one-time>
     |<-- користувач повертається в Mini App з start_param -->|
     |  POST /auth/telegram (initData містить start_param) -> сесія вже з токеном

Токен НІКОЛИ не потрапляє у фронтенд — тільки прапорець silpo_connected.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import get_settings
from app.db import repo


class OAuthError(RuntimeError):
    pass


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


_metadata_cache: dict[str, Any] | None = None


async def discover_metadata() -> dict[str, Any]:
    """RFC 8414 discovery. Спершу пробуємо метадані, прив'язані до MCP-ресурсу,
    потім issuer. Якщо нічого — падаємо на явні URL з .env."""
    global _metadata_cache
    if _metadata_cache is not None:
        return _metadata_cache

    s = get_settings()
    candidates = [
        # RFC 9728: protected resource metadata біля самого MCP
        "https://mcp.silpo.ua/.well-known/oauth-protected-resource",
        "https://mcp.silpo.ua/.well-known/oauth-authorization-server",
        f"{s.silpo_oauth_issuer.rstrip('/')}/.well-known/oauth-authorization-server",
        f"{s.silpo_oauth_issuer.rstrip('/')}/.well-known/openid-configuration",
    ]
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for url in candidates:
            try:
                r = await client.get(url)
            except httpx.HTTPError:
                continue
            if r.status_code != 200:
                continue
            try:
                data = r.json()
            except ValueError:
                continue
            # protected-resource metadata лише вказує на authorization_servers
            if "authorization_endpoint" not in data and data.get("authorization_servers"):
                issuer = data["authorization_servers"][0].rstrip("/")
                try:
                    rr = await client.get(f"{issuer}/.well-known/oauth-authorization-server")
                    if rr.status_code == 200:
                        data = rr.json()
                except httpx.HTTPError:
                    continue
            if "authorization_endpoint" in data and "token_endpoint" in data:
                _metadata_cache = data
                return data

    if s.silpo_oauth_authorize_url and s.silpo_oauth_token_url:
        _metadata_cache = {
            "authorization_endpoint": s.silpo_oauth_authorize_url,
            "token_endpoint": s.silpo_oauth_token_url,
        }
        return _metadata_cache

    raise OAuthError(
        "Не вдалось знайти OAuth-метадані Сільпо. Задай SILPO_OAUTH_AUTHORIZE_URL "
        "і SILPO_OAUTH_TOKEN_URL у .env (значення бери з документації хакатону)."
    )


def redirect_uri() -> str:
    return f"{get_settings().public_backend_url.rstrip('/')}/auth/silpo/callback"


async def ensure_client() -> dict[str, Any]:
    """client_id для OAuth: з .env, з кешу в БД або через Dynamic Client Registration.

    RFC 7591: POST на registration_endpoint з метаданими нашого застосунку.
    Реєструємось як public client (token_endpoint_auth_method="none") — секрет
    зберігати ніде не треба, бо PKCE і так зв'язує запит із нашим бекендом.
    """
    s = get_settings()
    if s.silpo_oauth_client_id:
        return {
            "client_id": s.silpo_oauth_client_id,
            "client_secret": s.silpo_oauth_client_secret or None,
            "auth_method": "client_secret_post" if s.silpo_oauth_client_secret else "none",
        }

    meta = await discover_metadata()
    issuer = meta.get("issuer", s.silpo_mcp_url)
    uri = redirect_uri()

    cached = await repo.get_oauth_client(issuer, uri)
    if cached:
        return cached

    registration_endpoint = meta.get("registration_endpoint")
    if not registration_endpoint:
        raise OAuthError(
            "Сервер не підтримує Dynamic Client Registration і SILPO_OAUTH_CLIENT_ID не заданий"
        )

    methods = meta.get("token_endpoint_auth_methods_supported") or ["none"]
    auth_method = "none" if "none" in methods else methods[0]

    payload = {
        "client_name": "Нутрі-Кошик (Telegram Mini App)",
        "redirect_uris": [uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": auth_method,
        "application_type": "web",
    }
    if s.silpo_oauth_scope:
        payload["scope"] = s.silpo_oauth_scope

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(registration_endpoint, json=payload)
    if r.status_code >= 400:
        raise OAuthError(f"registration_endpoint {r.status_code}: {r.text[:400]}")
    data = r.json()
    if "client_id" not in data:
        raise OAuthError(f"Відповідь /register без client_id: {str(data)[:300]}")

    await repo.save_oauth_client(
        issuer, uri, data["client_id"], data.get("client_secret"),
        data.get("token_endpoint_auth_method", auth_method), data,
    )
    return {
        "client_id": data["client_id"],
        "client_secret": data.get("client_secret"),
        "auth_method": data.get("token_endpoint_auth_method", auth_method),
    }


async def build_authorize_url(user_id: str) -> str:
    s = get_settings()
    meta = await discover_metadata()
    client = await ensure_client()
    verifier, challenge = _pkce_pair()
    state = await repo.save_oauth_state(user_id, verifier, redirect_uri())

    params = {
        "response_type": "code",
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri(),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if s.silpo_oauth_scope:
        params["scope"] = s.silpo_oauth_scope
    # MCP-специфічний параметр (RFC 8707) — прив'язує токен до ресурсу
    params["resource"] = s.silpo_mcp_url

    return str(httpx.URL(meta["authorization_endpoint"], params=params))


async def _post_token(payload: dict[str, str]) -> dict[str, Any]:
    meta = await discover_metadata()
    client = await ensure_client()

    auth = None
    if client.get("client_secret") and client.get("auth_method") == "client_secret_basic":
        auth = (client["client_id"], client["client_secret"])
    else:
        payload["client_id"] = client["client_id"]
        if client.get("client_secret"):
            payload["client_secret"] = client["client_secret"]

    async with httpx.AsyncClient(timeout=20.0) as client_http:
        r = await client_http.post(meta["token_endpoint"], data=payload, auth=auth)
    if r.status_code >= 400:
        raise OAuthError(f"token endpoint {r.status_code}: {r.text[:400]}")
    return r.json()


async def exchange_code(code: str, code_verifier: str) -> dict[str, Any]:
    return await _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "code_verifier": code_verifier,
            "resource": get_settings().silpo_mcp_url,
        }
    )


async def refresh(refresh_token: str) -> dict[str, Any]:
    return await _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "resource": get_settings().silpo_mcp_url,
        }
    )


async def get_valid_access_token(user_id: str) -> str | None:
    """Повертає живий access_token, за потреби роблячи refresh (401 -> refresh-флоу)."""
    tokens = await repo.get_tokens(user_id)
    if not tokens:
        return None
    if tokens["expires_at"] - timedelta(seconds=60) > datetime.now(UTC):
        return tokens["access_token"]
    if not tokens.get("refresh_token"):
        await repo.drop_tokens(user_id)
        return None
    data = await refresh(tokens["refresh_token"])
    await repo.save_tokens(
        user_id,
        data["access_token"],
        data.get("refresh_token") or tokens["refresh_token"],
        int(data.get("expires_in", 3600)),
        data.get("scope"),
        data.get("token_type", "Bearer"),
    )
    return data["access_token"]


async def force_refresh(user_id: str) -> str | None:
    tokens = await repo.get_tokens(user_id)
    if not tokens or not tokens.get("refresh_token"):
        return None
    data = await refresh(tokens["refresh_token"])
    await repo.save_tokens(
        user_id,
        data["access_token"],
        data.get("refresh_token") or tokens["refresh_token"],
        int(data.get("expires_in", 3600)),
        data.get("scope"),
        data.get("token_type", "Bearer"),
    )
    return data["access_token"]


def miniapp_return_url(startapp_token: str) -> str:
    s = get_settings()
    return f"https://t.me/{s.telegram_bot_username}/{s.telegram_webapp_short_name}?startapp={startapp_token}"
