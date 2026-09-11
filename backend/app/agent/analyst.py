"""Агент-аналітик: модель робить СУДЖЕННЯ, а не арифметику.

Розподіл праці, який визначає всю архітектуру:

  скрипт рахує ФАКТИ        дати покупок, різні дні, тижні, розриви,
                            ціни, економію, збіги алергенів
  модель ухвалює СУДЖЕННЯ   що з цього справді звичка, що варте показу,
                            чи має заміна сенс як ТОВАР, і якими словами

Чому не навпаки. Числа мають бути відтворюваними: те саме питання завтра має
дати ту саму суму, і цю суму треба вміти захистити. Але «чи має сенс міняти
стики Terea на Delia» — це не арифметика. Скрипт бачить два тютюнових вироби
схожої ціни й радіє. Модель знає, що стики прив'язані до пристрою і така
заміна фізично марна.

Кожне число з відповіді проходить через llm/sanitize: якщо його немає у
фактах, речення відкидається й береться детермінований запасний варіант.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.llm import sanitize
from app.llm.provider import LLMUnavailable, Step, get_provider

log = logging.getLogger("analyst")

MAX_ITEMS = 18
MAX_TOKENS = 900

# Скільки товарів даємо моделі на класифікацію. Це ВСІ кандидати, включно з
# тими, що скрипт відсіяв, — інакше модель лише коментує чужий вибір.
# Менше кандидатів, але кожен із коротким поясненням — інакше відповідь
# обривається на півслові й JSON стає нечитабельним. Перевірено: 40 товарів
# із розгорнутими поясненнями не влазять у ліміт виводу.
MAX_CANDIDATES = 26
CLASSIFY_TOKENS = 3200

SYSTEM = """Ти — аналітик покупок у застосунку «Сільпо». Тобі дають ФАКТИ про
покупки гостя, вже пораховані програмою. Твоя робота — судження, не рахунок.

ЗАБОРОНЕНО:
• вигадувати будь-які числа; можна вживати лише ті, що є у фактах
• моралізувати, радити «менше цукру», «пийте воду» чи оцінювати спосіб життя
• пропонувати заміну тютюну й алкоголю — марка стиків прив'язана до пристрою,
  а алкоголь є справою смаку

ЯК ДУМАТИ ПРО ЗВИЧКУ:
Звичка — це покупки, РОЗКИДАНІ в часі. Кілька рядків одного чека — це один
похід у магазин, а не кілька покупок. Дві покупки за три дні — епізод, а не ритм.

ПРО ЗАМІНИ:
Заміна має бути купованою в реальності: той самий тип товару, та сама роль у
кошику. Кола міняється на колу без цукру чи сік — ніколи на воду.

Відповідай ЛИШЕ валідним JSON без пояснень навколо."""

TEMPLATE = """ФАКТИ ПРО ГОСТЯ
{facts}

Поверни JSON такої форми:
{{
  "insight": "1-2 речення про те, ЯК ця людина купує. Конкретно, без моралі.",
  "items": [
    {{"slug": "...", "verdict": "habit|new|dropped|occasional",
      "why": "коротке пояснення людською мовою"}}
  ],
  "swaps": [
    {{"slug": "...", "keep": true|false,
      "why": "чому ця заміна має або не має сенсу як товар"}}
  ],
  "order": ["safety", "promo", "health", "alternative", "emerging", "fading"]
}}

В "items" вкажи лише ті товари, де твоє судження ДОДАЄ щось до фактів.
В "swaps" перевір кожну запропоновану заміну: чи її взагалі можна купити
замість оригіналу. Порядок у "order" — від найкориснішого для цього гостя."""


def _facts(plan: dict[str, Any]) -> dict[str, Any]:
    """Компактний зріз фактів. Усе пораховане нами, нічого зайвого."""
    items = []
    for item in (plan.get("items") or [])[:MAX_ITEMS]:
        habit = item.get("habit") or {}
        alt = item.get("alternative") or {}
        items.append({
            "slug": item.get("slug"),
            "name": item.get("name"),
            "category": item.get("category_label"),
            "price": item.get("price"),
            "days_bought": habit.get("days"),
            "different_weeks": habit.get("weeks"),
            "span_days": habit.get("span_days"),
            "days_since_last": habit.get("since_last_days"),
            "our_verdict": habit.get("kind"),
            "proposed_swap": {"name": alt.get("name"), "price": alt.get("price"),
                              "saves": alt.get("saved")} if alt else None,
        })
    profile = plan.get("profile") or {}
    summary = plan.get("summary") or {}
    return {
        "period_weeks": summary.get("based_on_weeks"),
        "receipts": summary.get("receipts"),
        "restrictions": [r.get("label") for r in (profile.get("restrictions") or [])],
        "items": items,
        "new_in_basket": [r.get("name") for r in (plan.get("emerging") or [])],
        "dropped_from_habit": [r.get("name") for r in (plan.get("fading") or [])],
    }


ITEM_RE = re.compile(r"\{[^{}]*?\"slug\"\s*:\s*\"[^\"]+\"[^{}]*?\}")


def _parse(raw: str) -> dict[str, Any] | None:
    """Читає JSON, а якщо відповідь обірвалась — рятує цілі обʼєкти.

    Модель іноді впирається в ліміт виводу й лишає JSON недописаним. Викидати
    через це всю класифікацію марно: цілі елементи в ній усе одно є.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        text = text.removeprefix("json").strip()

    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    rescued: dict[str, Any] = {}
    insight = re.search(r'"insight"\s*:\s*"([^"]{10,400})"', text)
    if insight:
        rescued["insight"] = insight.group(1)

    salvaged = []
    for chunk in ITEM_RE.findall(text):
        try:
            salvaged.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    if salvaged:
        rescued["items"] = salvaged
    if rescued:
        log.info("відповідь обірвана — врятовано %d елементів", len(salvaged))
        return rescued
    return None


async def analyse(plan: dict[str, Any], on_step=None) -> dict[str, Any]:
    """Повертає блок `agent` для плану. Ніколи не кидає — LLM необовʼязковий."""
    steps: list[dict[str, Any]] = []

    def note(text: str, kind: str = "think") -> None:
        steps.append({"kind": kind, "text": text})
        if on_step:
            on_step(Step(kind=kind, text=text))

    facts = _facts(plan)
    note(f"Читаю {facts['receipts']} чеків за {facts['period_weeks']} тижнів")
    if facts["restrictions"]:
        note(f"Враховую обмеження профілю: {', '.join(facts['restrictions']).lower()}")
    note(f"Оцінюю {len(facts['items'])} позицій: чи це звичка, чи збіг")

    try:
        provider = get_provider()
        raw = await provider.complete(
            SYSTEM, TEMPLATE.format(facts=json.dumps(facts, ensure_ascii=False)), MAX_TOKENS
        )
    except LLMUnavailable as exc:
        note(f"Модель недоступна ({exc}) — лишаю детерміновані пояснення", "answer")
        return {"available": False, "steps": steps, "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 — аналітик не має валити план
        log.warning("аналітик не відповів: %s", exc)
        note("Модель не відповіла — лишаю детерміновані пояснення", "answer")
        return {"available": False, "steps": steps, "reason": str(exc)[:200]}

    parsed = _parse(raw)
    if not parsed:
        note("Відповідь моделі нечитабельна — лишаю детерміновані пояснення", "answer")
        return {"available": False, "steps": steps, "reason": "не JSON"}

    allowed = sanitize.allowed_numbers(facts)
    dropped = 0

    def clean(text: str) -> str | None:
        nonlocal dropped
        text = (text or "").strip()
        if not text:
            return None
        bad = sanitize.check(text, allowed)
        if bad:
            dropped += 1
            return None
        return text

    insight = clean(parsed.get("insight", ""))
    verdicts = {}
    for row in parsed.get("items") or []:
        why = clean(row.get("why", ""))
        if row.get("slug") and why:
            verdicts[row["slug"]] = {"verdict": row.get("verdict"), "why": why}

    swaps = {}
    for row in parsed.get("swaps") or []:
        why = clean(row.get("why", ""))
        if row.get("slug") and why:
            swaps[row["slug"]] = {"keep": bool(row.get("keep", True)), "why": why}

    rejected = [s for s in swaps.values() if not s["keep"]]
    if rejected:
        note(f"Відхилив {len(rejected)} заміни: не куповані в реальності", "answer")
    if dropped:
        note(f"Відкинув {dropped} формулювання: у них були числа не з наших фактів", "answer")
    note("Готово", "answer")

    return {
        "available": True,
        "provider": provider.name,
        "insight": insight,
        "verdicts": verdicts,
        "swaps": swaps,
        "order": [k for k in (parsed.get("order") or []) if isinstance(k, str)],
        "numbers_rejected": dropped,
        "steps": steps,
    }


CLASSIFY_SYSTEM = """Ти — аналітик покупок. Тобі дають список товарів і ТОЧНІ ДАТИ,
коли гість їх купував. Твоя робота — вирішити, що з цього справді звичка.

ЩО ТАКЕ ЗВИЧКА:
• покупки РОЗКИДАНІ в часі, а не злиплі в один похід;
• повторюються останнім часом, а не колись давно;
• кілька дат в один тиждень — це один епізод, а не ритм.

ТИПИ:
  habit      бере регулярно і зараз — можна класти в кошик
  new        почали брати нещодавно, ритму ще не видно
  dropped    раніше брали регулярно, тепер ні
  occasional випадкова або надто рідка покупка

Думай як людина, що дивиться на чужий список покупок, а не як лічильник.
Сезонність, вихідні, закупівля про запас — усе це має значення.
Відповідай ЛИШЕ валідним JSON."""

CLASSIFY_TEMPLATE = """Період спостереження: {period_days} днів. Сьогодні {today}.

ТОВАРИ Й ДАТИ ПОКУПОК
{rows}

Поверни JSON:
{{"items": [{{"slug": "...", "verdict": "habit|new|dropped|occasional",
              "why": "максимум 8 слів, без чисел"}}]}}

Дай вердикт КОЖНОМУ товару зі списку."""


def _rows_for_classify(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda r: -(r.get("spend") or 0))[:MAX_CANDIDATES]
    return [
        {
            "slug": r.get("slug"),
            "name": (r.get("name") or "")[:60],
            "dates": r.get("days") or [],
            "units": round(float(r.get("total_qty") or 0)),
            "our_guess": (r.get("habit") or {}).get("kind"),
        }
        for r in ranked
    ]


async def classify(
    rows: list[dict[str, Any]], period_days: int, today: str, on_step=None
) -> dict[str, dict[str, Any]]:
    """Вердикт моделі по КОЖНОМУ товару, включно з відсіяними скриптом.

    Порожній словник означає «модель не змогла» — тоді лишається рішення
    скрипта. Це не аварія: детермінований шар самодостатній.
    """
    payload = _rows_for_classify(rows)
    if not payload:
        return {}
    if on_step:
        on_step(Step(kind="think", text=f"Класифікую {len(payload)} товарів за датами покупок"))

    try:
        provider = get_provider()
        raw = await provider.complete(
            CLASSIFY_SYSTEM,
            CLASSIFY_TEMPLATE.format(
                period_days=period_days, today=today,
                rows=json.dumps(payload, ensure_ascii=False),
            ),
            CLASSIFY_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("класифікація не вдалась: %s", exc)
        return {}

    parsed = _parse(raw)
    if not parsed:
        log.warning("класифікація нечитабельна, довжина відповіді %d", len(raw or ""))
        return {}

    allowed = sanitize.allowed_numbers(payload)
    out: dict[str, dict[str, Any]] = {}
    for row in parsed.get("items") or []:
        slug = row.get("slug")
        verdict = row.get("verdict")
        if not slug or verdict not in {"habit", "new", "dropped", "occasional"}:
            continue
        why = (row.get("why") or "").strip()
        if why and sanitize.check(why, allowed):
            why = ""          # вигадане число — лишаємо вердикт, прибираємо текст
        out[slug] = {"verdict": verdict, "why": why}
    return out


PICK_SYSTEM = """Ти добираєш товари для поради в застосунку «Сільпо».

Тобі дають КАТЕГОРІЮ, якої гостю бракує, список знайдених у каталозі товарів
і те, що гість купує регулярно. Обери 2-3 товари, які людина реально візьме.

ПРАВИЛА:
• товар має справді належати до категорії. Банановий йогурт — це молочка,
  а не фрукт; сік — це напій, а не фрукт;
• не пропонуй дитяче харчування, корми, приправи й готові страви;
• зважай на те, що гість уже купує: якщо він бере сулугуні й моцарелу,
  логічніше запропонувати те, що поєднається з цим;
• дешевше й акційне краще — але не ціною сенсу;
• якщо жоден товар не підходить — поверни порожній список, це нормально.

Порада має бути ЗДІЙСНЕННОЮ: не «додайте 1178 ₴ овочів», а конкретна дія.
Без чисел у тексті поради. Відповідай ЛИШЕ валідним JSON."""

PICK_TEMPLATE = """КАТЕГОРІЯ, ЯКОЇ БРАКУЄ: {category}
ГІСТЬ РЕГУЛЯРНО КУПУЄ: {habits}

ЗНАЙДЕНІ ТОВАРИ
{candidates}

Поверни JSON:
{{"picks": ["slug", "slug"], "advice": "одне речення, що саме варто взяти"}}"""


async def pick_products(
    category: str, candidates: list[dict[str, Any]], habits: list[str]
) -> dict[str, Any]:
    """Модель обирає товари для поради. Порожній результат — валідна відповідь."""
    if not candidates:
        return {}
    short = [
        {"slug": c.get("slug"), "name": (c.get("name") or "")[:64],
         "price": c.get("price"), "promo": bool(c.get("on_promotion"))}
        for c in candidates[:24]
    ]
    try:
        provider = get_provider()
        raw = await provider.complete(
            PICK_SYSTEM,
            PICK_TEMPLATE.format(
                category=category,
                habits=", ".join(habits[:8]) or "—",
                candidates=json.dumps(short, ensure_ascii=False),
            ),
            600,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("добір товарів не вдався: %s", exc)
        return {}

    parsed = _parse(raw) or {}
    picks = [p for p in (parsed.get("picks") or []) if isinstance(p, str)]
    advice = (parsed.get("advice") or "").strip()
    if advice and sanitize.check(advice, sanitize.allowed_numbers(short)):
        advice = ""
    return {"picks": picks, "advice": advice}
