from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db.supabase import db
from app.services import digest
from app.routers import (
    agent, auth, basket, bot, cart, debug, insights, live, metrics, nutrition,
    plan, reminders, settings as settings_router, swaps, trends, week,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Дайджест прокидається сам. Задача переживає падіння окремого проходу,
    # а вимикається прапорцем — щоб тести й локальна розробка не слали нічого.
    sweep = None
    if get_settings().enable_digest:
        sweep = asyncio.create_task(digest.sweep_forever())
    yield
    if sweep is not None:
        sweep.cancel()
        with suppress(asyncio.CancelledError):
            await sweep
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
app.include_router(agent.router)
app.include_router(insights.router)
app.include_router(plan.router)
app.include_router(settings_router.router)
app.include_router(basket.router)
app.include_router(nutrition.router)
app.include_router(reminders.router)
app.include_router(metrics.router)
app.include_router(live.router)


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

    # Перші сегменти всіх зареєстрованих API-маршрутів: settings, cart, plan…
    API_SEGMENTS = {
        route.path.strip("/").split("/")[0]
        for route in app.routes
        if getattr(route, "path", "").strip("/")
    } - {"", "{path:path}"}

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        candidate = FRONTEND_DIST / path
        if candidate.is_file():
            return FileResponse(candidate)

        # Невідомий шлях ПІД API-сегментом — це відсутній маршрут, а не екран
        # застосунку. Раніше сюди приходив index.html з кодом 200: фронтенд
        # отримував HTML замість JSON, падав на розборі й мовчки показував
        # порожній екран. Через це застарілий процес бекенду виглядав як
        # «налаштування не зберігаються» замість «маршруту не існує».
        if path.strip("/").split("/")[0] in API_SEGMENTS:
            return JSONResponse(
                status_code=404,
                content={
                    "detail": f"Маршрут /{path} не існує. "
                              "Найімовірніше, бекенд запущено зі старим кодом — перезапустіть його."
                },
            )
        return FileResponse(FRONTEND_DIST / "index.html")
