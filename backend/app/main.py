from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db.supabase import db
from app.routers import auth, bot, cart, debug, swaps, trends, week

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await db().aclose()


settings = get_settings()

app = FastAPI(
    title="Нутрі-Кошик API",
    description=(
        "Бекенд Telegram Mini App для хакатону «Сільпо AI Factory». "
        "Усі дані про покупки надходять виключно з офіційного MCP "
        f"({settings.silpo_mcp_url}); OAuth-токени гостя зберігаються тільки тут, "
        "у зашифрованому вигляді, і ніколи не потрапляють у фронтенд."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cart.router)
app.include_router(trends.router)
app.include_router(swaps.router)
app.include_router(debug.router)
app.include_router(bot.router)
app.include_router(week.router)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "mcp_endpoint": settings.silpo_mcp_url,
        "supabase": db().enabled,
        "telegram_bot_configured": bool(settings.telegram_bot_token),
    }


# --- Статика Mini App -------------------------------------------------------
# Фронтенд віддається ЦИМ ЖЕ сервером: один домен на API і на застосунок.
# Так немає CORS, не потрібен другий тунель, і в проді це один деплой.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str) -> FileResponse:
        candidate = FRONTEND_DIST / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
