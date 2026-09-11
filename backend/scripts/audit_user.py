"""Аудит звичок одного гостя — інструмент налагодження.

Відповідає на питання «я ж завжди це беру, чому його немає в наборі?»:
показує реальні дати покупок і ту саму перевірку, яку товар проходив
у конвеєрі. Нічого не вирішує наново — лише робить рішення видимим.

    cd backend
    .venv/bin/python scripts/audit_user.py --list
    .venv/bin/python scripts/audit_user.py --user <telegram_id> --find вівсян --find комбуч

Читає лише той акаунт, який ви вкажете. Запускайте за згодою його власника.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def list_users() -> int:
    from app.db.supabase import db

    users = await db().select("users", {})
    tokens = {t["user_id"] for t in await db().select("silpo_oauth_tokens", {})}
    print(f"{'імя':<16}{'telegram_id':>14}   Сільпо")
    for u in users:
        mark = "підключено" if u["id"] in tokens else "—"
        print(f"{str(u.get('first_name') or '?'):<16}{str(u.get('telegram_id')):>14}   {mark}")
    await db().aclose()
    return 0


async def audit(telegram_id: int, needles: list[str], top: int) -> int:
    from app.db import repo
    from app.db.supabase import db
    from app.mcp.gateway import silpo
    from app.services import explain_habit, habits, kinds
    from app.services import noise as noise_filter
    from app.services import plan as plan_service
    from app.services.cart_analysis import fetch_cart

    user = await repo.get_user_by_telegram_id(telegram_id)
    if not user:
        print("Такого користувача немає"); return 1

    print(f"АКАУНТ: {user.get('first_name')} · telegram {telegram_id}\n")
    async with silpo(user["id"]) as api:
        ctx, _cart, meta = await fetch_cart(api)
        if ctx is None:
            print("Дані Сільпо недоступні:", meta.get("reason")); return 1
        orders = await habits.fetch_offline_orders(api, ctx)

    if not orders:
        print("Чеків не знайдено"); return 1

    period = max((orders[0].created_at - orders[-1].created_at).days, 1)
    print(f"ЧЕКІВ: {len(orders)} за {period} дн. "
          f"({orders[-1].created_at.date()} → {orders[0].created_at.date()})\n")

    rows = plan_service._aggregate(orders)
    grouped = kinds.group(rows)
    split = noise_filter.split(grouped, receipts=len(orders), period_days=period)
    basket_kinds = {r.get("kind_key") for r in split["basket"]}

    print(f"=== ТОП-{top} ВИДІВ ЗА КІЛЬКІСТЮ ДНІВ ПОКУПКИ ===")
    print(f"{'вид':<16}{'днів':>6}{'марок':>7}{'витрати':>10}  {'у наборі':<10} причина")
    for g in sorted(grouped, key=lambda r: -len(r.get('days') or []))[:top]:
        kind = g.get("kind_key")
        inb = "ТАК" if kind in basket_kinds else "ні"
        print(f"  {str(kind)[:14]:<16}{g['times']:>4}{g.get('kind_brands', 1):>7}"
              f"{g.get('spend', 0):>9.0f} ₴  {inb:<10} {str(g.get('kind_reason'))[:44]}")

    for needle in needles:
        print(f"\n=== ДЕТАЛЬНО: «{needle}» ===")
        result = explain_habit.explain(rows, needle, period, date.today())
        if not result["matches"]:
            print(f"  у чеках нічого не знайдено (шукали підрядок «{needle}»)")
            continue
        print(f"  правила: звичка = {result['rules']['stable_min_days']} покупок "
              f"у {result['rules']['stable_min_weeks']} різних тижнях "
              f"за останні {result['window_days']} дн.")
        for m in result["matches"]:
            print(f"\n  {m['name']}")
            print(f"     вид «{m['kind']}» · марок у виді: {m['brands_in_kind']}")
            print(f"     дати покупок: {', '.join(m['purchase_days'])}")
            print(f"     днів усього: {m['days_total']} · у виді: {m['days_in_kind']} "
                  f"· за квартал: {m['days_recent']} у {m['weeks_recent']} тижнях")
            print(f"     цикл категорії: ~{m['cycle_days']} дн.")
            print(f"     ВЕРДИКТ: {m['verdict_label']} — {m['explanation']}")
            if m["why_not"]:
                print(f"     ЧОМУ НЕ В НАБОРІ: {m['why_not']}")

    await db().aclose()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="показати під'єднані акаунти")
    ap.add_argument("--user", type=int, help="telegram_id гостя")
    ap.add_argument("--find", action="append", default=[], help="шукати товар (можна кілька)")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()

    if a.list:
        return asyncio.run(list_users())
    if not a.user:
        ap.print_help(); return 1
    return asyncio.run(audit(a.user, a.find or ["вівсян", "комбуч"], a.top))


if __name__ == "__main__":
    raise SystemExit(main())
