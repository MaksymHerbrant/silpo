"""Наскрізний smoke-тест у DEMO_MODE: онбординг -> аналіз -> тренд -> своп -> лог.

Запуск:  cd backend && .venv/bin/python scripts/smoke_demo.py
Живий MCP не потрібен: дані беруться з app/mcp/fixtures.py.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BOT_TOKEN = "123456:TEST-BOT-TOKEN"
os.environ.update(
    DEMO_MODE="true",
    TELEGRAM_BOT_TOKEN=BOT_TOKEN,
    SESSION_SECRET="smoke-secret",
    TOKEN_ENCRYPTION_KEY="smoke-test-passphrase",
    ENABLE_LLM_EXPLANATIONS="false",
    SUPABASE_URL="",
    SUPABASE_SERVICE_ROLE_KEY="",
)


def make_init_data(telegram_id: int = 777001) -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE",
        "user": json.dumps(
            {"id": telegram_id, "first_name": "Тест", "username": "tester", "language_code": "uk"},
            ensure_ascii=False, separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


async def main() -> int:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        health = (await c.get("/health")).json()
        print("health:", health)

        # 1. Підробний initData має бути відхилений
        bad = await c.post("/auth/telegram", json={"init_data": make_init_data().replace("hash=", "hash=0")})
        assert bad.status_code == 401, bad.text
        print("initData spoof rejected:", bad.status_code)

        # 2. Валідний initData -> сесія
        r = await c.post("/auth/telegram", json={"init_data": make_init_data()})
        r.raise_for_status()
        auth = r.json()
        headers = {"Authorization": f"Bearer {auth['token']}"}
        print("auth ok, silpo_connected =", auth["silpo_connected"])

        # 3. tools/list
        tools = (await c.get("/debug/tools", headers=headers)).json()
        print("tools/list:", tools["count"], "tools")

        # 4. Аналіз кошика
        a = await c.get("/cart/analysis", headers=headers, params={"explain_text": "true"})
        a.raise_for_status()
        analysis = a.json()
        print(f"score={analysis['score']} ({analysis['letter']}), "
              f"coverage={analysis['coverage']}, added_sugar={analysis['totals']['added_sugar']} г")
        print("summary:", analysis.get("summary_text"))
        for i in analysis["items"]:
            print(f"   - {i['title'][:38]:40} score={i['score']} {i.get('note') or ''}")

        # 5. Алергени
        allerg = (await c.get("/cart/allergens", headers=headers)).json()
        print("restrictions:", allerg["restrictions"])
        print("warnings:", [(w["product_title"], w["restriction"]) for w in allerg["warnings"]])

        # 6. Тренд
        tr = (await c.get("/trends/weekly", headers=headers, params={"refresh": "true"})).json()
        print("weeks:", [(w["week_start_date"], w["health_score"]) for w in tr["weeks"]],
              "delta:", tr["delta_vs_prev_week"])

        # 7. Свопи
        sw = (await c.get("/swaps/suggestions", headers=headers)).json()
        for s in sw["suggestions"]:
            print(f"swap: {s['original_title']} -> {s['suggested_title']} | {s['reason']}")
        assert sw["suggestions"], "жодної пропозиції заміни не згенеровано"

        # 8. Застосування свопу (write-виклик у MCP)
        applied = (await c.post(f"/swaps/{sw['suggestions'][0]['id']}/apply", headers=headers)).json()
        print("apply:", applied["applied"], "cart:", applied["cart_id"])
        print("acceptance stats:", (await c.get("/swaps/suggestions", headers=headers,
                                                params={"rebuild": "false"})).json()["stats"])

        # 9. Лог JSON-RPC
        log = (await c.get("/debug/mcp-log", headers=headers, params={"limit": 100})).json()
        print("mcp calls logged:", len(log["entries"]))
        print("last call:", json.dumps(log["entries"][0]["jsonrpc_request"], ensure_ascii=False)[:160])
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
