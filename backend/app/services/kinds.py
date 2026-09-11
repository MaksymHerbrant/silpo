"""Звичка живе на рівні ВИДУ товару, а не конкретної марки.

Спостереження, з якого це виросло. За рік покупок:

    сир      21 день, 19 різних марок, найпопулярніша — 29%
    чипси    16 днів, 14 марок, найпопулярніша — 19%
    сметана  11 днів,  8 марок, найпопулярніша — 18%

Людина не думає «беру моцарелу Ферма». Вона думає «беру сир». Марка щоразу
інша — та, що трапилась або була в акції. Рахуючи звичку по SKU, ми бачили
двадцять слабких сигналів замість одного сильного і викидали їх усі як шум.

Але це не універсально. Поруч у тих самих чеках:

    лимон  100% однієї позиції
    томат   92%
    хліб    71%

Тут марка принципова — пропонувати «інший хліб, бо він в акції» безглуздо.

Звідси головний висновок для продукту: частка найпопулярнішої марки всередині
виду — це і є ЛОЯЛЬНІСТЬ. Низька лояльність означає, що гостю байдужа марка,
і йому доречно запропонувати ту, що зараз в акції. Висока — що марка є
частиною звички, і чіпати її не варто.
"""
from __future__ import annotations

import re
from typing import Any

# Назви українських товарів починаються з виду: «Сир Ферма Моцарелла…».
# Тому вид — це перше значуще слово, зведене до єдиного написання.
ALIASES: dict[str, str] = {
    "чипси": "чіпси", "чіпcи": "чіпси",
    "напій": "напій", "напої": "напій",
    "яйце": "яйця", "яєць": "яйця",
    "виріб": "тютюн",          # «Виріб тютюновий для електричного нагрівання»
    "вироби": "макарони",      # «Вироби макаронні»
    "снек": "снеки", "снеки": "снеки",
    "хлібці": "хлібці",
}

# Слова, які не є видом товару: з них назва не починається змістовно
NOT_A_KIND = frozenset({"з", "для", "та", "і", "у", "в", "на", "по", "від"})

# Нижче цієї частки найпопулярнішої марки вважаємо, що гостю байдужа марка
LOYALTY_THRESHOLD = 0.5
# Вид, у якому менше стількох марок, не вважаємо «байдужим до марки»
MIN_BRANDS_FOR_INDIFFERENT = 3


def kind_of(name: str) -> str:
    """Вид товару — перше значуще слово назви."""
    cleaned = re.sub(r"[«»\"'()]", " ", (name or "").lower())
    for word in cleaned.split():
        word = word.strip(".,:;-–—")
        if len(word) < 3 or word in NOT_A_KIND:
            continue
        return ALIASES.get(word, word)
    return "інше"


def group(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Зводить SKU в види товару, зберігаючи форму рядка для решти конвеєра.

    Повертає рядки того ж вигляду, що й `_aggregate`, але `slug`/`name` — це
    представник виду, а `days` — обʼєднання днів усіх марок цього виду.
    """
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(kind_of(row.get("name") or ""), []).append(row)

    out: list[dict[str, Any]] = []
    for kind, members in buckets.items():
        members = sorted(members, key=lambda r: (-len(r.get("days") or []), -(r.get("spend") or 0)))
        days: set[str] = set()
        history: list[dict[str, Any]] = []
        for member in members:
            days.update(member.get("days") or [])
            history.extend(member.get("history") or [])

        top = members[0]
        top_days = len(top.get("days") or [])
        loyalty = top_days / len(days) if days else 1.0
        indifferent = (
            len(members) >= MIN_BRANDS_FOR_INDIFFERENT and loyalty < LOYALTY_THRESHOLD
        )

        out.append({
            **top,
            "days": sorted(days),
            "times": len(days),
            "total_qty": sum(float(m.get("total_qty") or 0) for m in members),
            "spend": sum(float(m.get("spend") or 0) for m in members),
            "history": sorted(history, key=lambda h: h.get("date") or ""),
            "kind_key": kind,
            "kind_brands": len(members),
            "loyalty": round(loyalty, 2),
            "brand_indifferent": indifferent,
            "members": [
                {"slug": m.get("slug"), "name": m.get("name"),
                 "days": len(m.get("days") or []), "spend": round(m.get("spend") or 0, 2)}
                for m in members[:8]
            ],
        })

    out.sort(key=lambda r: -(r.get("spend") or 0))
    return out


def describe(row: dict[str, Any]) -> str:
    """Людський опис звички на рівні виду."""
    kind = row.get("kind_key") or "товар"
    brands = row.get("kind_brands") or 1
    if row.get("brand_indifferent"):
        return f"берете {kind}, марка щоразу інша — {brands} різних за період"
    if brands > 1:
        return f"берете {kind}, майже завжди ту саму марку"
    return f"берете {kind}"
