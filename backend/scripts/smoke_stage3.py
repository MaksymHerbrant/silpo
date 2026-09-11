"""Smoke-тест етапів 3–5: онбординг, поріг, кошик, чіп, цикли, дайджест.

Живий MCP не потрібен — усе, що перевіряємо, працює на сховищі застосунку.
Запуск:  cd backend && .venv/bin/python scripts/smoke_stage3.py
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
    DEMO_MODE="true", TELEGRAM_BOT_TOKEN=BOT_TOKEN, SESSION_SECRET="smoke-secret",
    TOKEN_ENCRYPTION_KEY="smoke-test-passphrase", ENABLE_LLM_EXPLANATIONS="false",
    SUPABASE_URL="", SUPABASE_SERVICE_ROLE_KEY="",
)


def make_init_data(telegram_id: int = 777003) -> str:
    fields = {
        "auth_date": str(int(time.time())), "query_id": "AAE",
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
        session = (await c.post("/auth/telegram", json={"init_data": make_init_data()})).json()
        h = {"Authorization": f"Bearer {session['token']}"}

        # --- 1. Новий гість не проходив онбординг ---
        s = (await c.get("/settings", headers=h)).json()
        assert s["onboarded"] is False, "новий гість має побачити онбординг"
        assert s["price_tolerance"] == 0.05, s
        assert s["mode"] == "auto", "дефолт — автопілот"
        assert len(s["options"]["price_tolerance"]) == 4
        print(f"1. новий гість: онбординг={not s['onboarded']}, "
              f"дефолт={s['price_tolerance_label']}, режим={s['mode']}")

        # --- 2. Пропуск онбордингу = робочий дефолт ---
        s = (await c.put("/settings", headers=h, json={"onboarded": True})).json()
        assert s["onboarded"] is True and s["mode"] == "auto"
        # Пропуск НЕ має мовчки перемикати поріг у «без обмежень»
        assert s["price_tolerance"] == 0.05, f"пропуск зламав поріг: {s}"
        print(f"2. пропуск онбордингу → режим {s['mode']}, поріг {s['price_tolerance_label']}")

        # --- 3. Зміна порогу ---
        s = (await c.put("/settings", headers=h, json={"price_tolerance": 10, "mode": "saving"})).json()
        assert s["price_tolerance"] == 0.10 and s["price_tolerance_key"] == "medium", s
        s = (await c.put("/settings", headers=h, json={"unlimited_price": True})).json()
        assert s["price_tolerance"] is None and s["price_tolerance_label"] == "без обмежень"
        s = (await c.put("/settings", headers=h, json={"price_tolerance": 0})).json()
        assert s["price_tolerance"] == 0.0 and s["price_tolerance_label"] == "тільки не дорожче"
        print("3. поріг: 10% → без обмежень → тільки не дорожче ✓")

        # --- 4. Спільний кошик ---
        assert (await c.get("/cart", headers=h)).json()["count"] == 0
        await c.post("/cart/items", headers=h,
                     json={"product_id": "p1", "name": "Молоко", "price": 40, "source": "plan"})
        await c.post("/cart/items", headers=h,
                     json={"product_id": "p2", "name": "Хліб", "price": 25, "source": "nutrition"})
        # той самий товар з іншого екрана — не дубль, а +1 до кількості
        cart = (await c.post("/cart/items", headers=h,
                             json={"product_id": "p1", "name": "Молоко", "price": 40,
                                   "source": "promo"})).json()
        assert cart["positions"] == 2 and cart["count"] == 3, cart
        assert cart["total"] == 105.0, cart
        print(f"4. кошик з двох екранів: {cart['positions']} позиції, "
              f"{cart['count']} шт, {cart['total']} ₴")

        # --- 5. Кількість і видалення ---
        item = next(i for i in cart["items"] if i["product_id"] == "p1")
        cart = (await c.patch(f"/cart/items/{item['id']}", headers=h, json={"quantity": 5})).json()
        assert cart["count"] == 6, cart
        cart = (await c.delete(f"/cart/items/{item['id']}", headers=h)).json()
        assert cart["positions"] == 1 and cart["count"] == 1, cart
        # нуль == видалити
        other = cart["items"][0]
        cart = (await c.patch(f"/cart/items/{other['id']}", headers=h, json={"quantity": 0})).json()
        assert cart["positions"] == 0, cart
        print("5. кількість, видалення, нуль-як-видалення ✓")

        # --- 6. Пасивний чіп корисності ---
        r = (await c.get("/cart/rating", headers=h)).json()
        assert r["rating"] is None, "порожній кошик не має рейтингу"
        await c.post("/cart/items", headers=h,
                     json={"product_id": "c1", "name": "Чіпси Pringles", "price": 100, "quantity": 3})
        await c.post("/cart/items", headers=h,
                     json={"product_id": "c2", "name": "Молоко Премія", "price": 40, "quantity": 1})
        r = (await c.get("/cart/rating", headers=h)).json()["rating"]
        assert r["tone"] == "watch" and 1 <= r["score"] <= 10, r
        print(f"6. чіп кошика: {r['score']}/10 — {r['label']}")

        # Непродуктовий кошик рейтингу не отримує — і це чесніше, ніж вигадати
        await c.delete(f"/cart/items/{(await c.get('/cart', headers=h)).json()['items'][0]['id']}",
                       headers=h)
        await c.delete(f"/cart/items/{(await c.get('/cart', headers=h)).json()['items'][0]['id']}",
                       headers=h)
        await c.post("/cart/items", headers=h,
                     json={"product_id": "h1", "name": "Папір туалетний", "price": 200})
        assert (await c.get("/cart/rating", headers=h)).json()["rating"] is None
        print("7. кошик без їжі — рейтингу немає, нічого не вигадуємо")
        await c.delete(f"/cart/items/{(await c.get('/cart', headers=h)).json()['items'][0]['id']}",
                       headers=h)

        # --- 8. Нагадування без побудованого плану чесно кажуть «будується» ---
        r = (await c.get("/reminders", headers=h)).json()
        assert r.get("building") is True or r.get("has_data") is False, r
        print("8. нагадування без плану:", "building" if r.get("building") else r.get("reason"))

        # --- 9. Порожній кошик не оформлюється ---
        r = await c.post("/cart/checkout", headers=h)
        assert r.status_code == 400, r.status_code
        print("9. порожній кошик відхиляється:", r.status_code)

    print("\nЕТАПИ 3–5 OK — онбординг, поріг, кошик, чіп і нагадування — як задумано")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
