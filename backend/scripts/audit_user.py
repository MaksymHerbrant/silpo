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


async def audit(telegram_id: int, needles: list[str], top: int,
                show_all: bool = False, raw_date: str | None = None,
                check_online: bool = False) -> int:
    from app.db import repo
    from app.db.supabase import db
    from app.mcp.gateway import silpo
    from app.services import explain_habit, habit_model, habits, kinds
    from app.services import noise as noise_filter
    from app.services import plan as plan_service
    from app.mcp.client import McpNotConnected
    from app.services.cart_analysis import fetch_cart

    user = await repo.get_user_by_telegram_id(telegram_id)
    if not user:
        print("Такого користувача немає"); return 1

    print(f"АКАУНТ: {user.get('first_name')} · telegram {telegram_id}\n")
    try:
        async with silpo(user["id"]) as api:
            ctx, _cart, meta = await fetch_cart(api)
            if ctx is None:
                print("Дані Сільпо недоступні:", meta.get("reason")); return 1
            orders = await habits.fetch_offline_orders(api, ctx)
    except McpNotConnected:
        print("Цей гість не підʼєднав акаунт Сільпо — читати нема чого.")
        print("Список підключених: scripts/audit_user.py --list")
        return 1

    if not orders:
        print("Чеків не знайдено"); return 1

    period = max((orders[0].created_at - orders[-1].created_at).days, 1)
    print(f"ЧЕКІВ: {len(orders)} за {period} дн. "
          f"({orders[-1].created_at.date()} → {orders[0].created_at.date()})\n")

    rows = plan_service._aggregate(orders)
    grouped = kinds.group(rows)
    split = noise_filter.split(grouped, receipts=len(orders), period_days=period)
    basket_kinds = {r.get("kind_key") for r in split["basket"]}

    # Беремо рядки ПІСЛЯ split — у них є вердикт і пояснення
    decided = {r.get("kind_key"): r for r in split["basket"] + split["noise"]}
    today = date.today()
    cutoff = today.toordinal() - habit_model.RECENT_WINDOW_DAYS

    print(f"=== ТОП-{top} ВИДІВ ===")
    print(f"{'вид':<14}{'днів':>5}{'за 90д':>7}{'тижнів':>7}{'марок':>6}"
          f"{'витрати':>9}  {'набір':<7} обличчя виду / причина")
    for g in sorted(grouped, key=lambda r: -len(r.get("days") or []))[:top]:
        kind = g.get("kind_key")
        days = g.get("days") or []
        recent = [d for d in days if date.fromisoformat(d).toordinal() >= cutoff]
        weeks = len({date.fromisoformat(d).isocalendar()[:2] for d in recent})
        row = decided.get(kind) or {}
        inb = "ТАК" if kind in basket_kinds else "ні"
        face = str(row.get("name") or g.get("name") or "")[:30]
        print(f"  {str(kind)[:12]:<14}{len(days):>5}{len(recent):>7}{weeks:>7}"
              f"{g.get('kind_brands', 1):>6}{g.get('spend', 0):>8.0f} ₴  {inb:<7} {face}")
        if row.get("kind_reason"):
            print(f"{'':<14}{'':>32} {str(row['kind_reason'])[:70]}")

    print("\n=== ЩО САМЕ ПОТРАПИЛО В НАБІР ===")
    for r in split["basket"]:
        members = r.get("members") or []
        print(f"  вид «{r.get('kind_key')}» → показуємо: {str(r.get('name'))[:44]}")
        print(f"     марок у виді: {r.get('kind_brands')} · вірність: {r.get('loyalty')} "
              f"· марка байдужа: {r.get('brand_indifferent')}")
        for m in members[:8]:
            print(f"       {m['days']} дн. · {m['spend']:>6.0f} ₴ · {str(m['name'])[:44]}")

    if raw_date:
        print(f"\n=== СИРИЙ ЧЕК ЗА {raw_date} (як його віддає MCP) ===")
        hit = [o for o in orders if o.created_at.date().isoformat() == raw_date]
        if not hit:
            print("  чека за цю дату серед офлайн-чеків немає")
            print("  дати наявних:", ", ".join(
                sorted({o.created_at.date().isoformat() for o in orders})))
        for o in hit:
            print(f"  {o.created_at} · {o.total} ₴ · знижка {o.discount} ₴ · {o.branch}")
            for line in o.items:
                print(f"     {line.get('quantity')}× {line.get('price')} ₴  "
                      f"{str(line.get('name'))[:52]}  slug={line.get('slug')}")

    if check_online:
        print("\n=== ОНЛАЙН-ЗАМОВЛЕННЯ (доставка) ===")
        async with silpo(user["id"]) as api2:
            ctx2, _c, _m = await fetch_cart(api2)
            payload = await api2.call("silpo_get_my_online_orders",
                                      ctx2.as_args(limit=10, offset=0))
        import json as _json
        text = payload if isinstance(payload, str) else _json.dumps(payload, ensure_ascii=False)
        print("  ", text[:900])

    if show_all:
        print("\n=== УСІ ТОВАРИ З ЧЕКІВ ===")
        print(f"{'днів':>5}{'к-ть':>6}{'витрати':>9}  {'вид':<12} товар")
        for r in sorted(rows, key=lambda x: (-len(x.get("days") or []), -(x.get("spend") or 0))):
            days = r.get("days") or []
            print(f"{len(days):>5}{r.get('total_qty', 0):>6.0f}{r.get('spend', 0):>8.0f} ₴  "
                  f"{kinds.kind_of(r.get('name') or ''):<12} {str(r.get('name'))[:52]}")
            if len(days) > 1:
                print(f"{'':>21}  {'':<12} дати: {', '.join(days)}")
        print(f"\nусього різних товарів: {len(rows)}")

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
    ap.add_argument("--all", action="store_true", help="вивести УСІ товари з датами")
    ap.add_argument("--raw", help="сирий чек за дату, напр. 2026-07-06")
    ap.add_argument("--online", action="store_true", help="перевірити онлайн-замовлення")
    a = ap.parse_args()

    if a.list:
        return asyncio.run(list_users())
    if not a.user:
        ap.print_help(); return 1
    return asyncio.run(audit(a.user, a.find or [], a.top, a.all, a.raw, a.online))


if __name__ == "__main__":
    raise SystemExit(main())
