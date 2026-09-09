"""Персональні норми: скільки гостю треба їсти під його ціль.

Без цілі будь-яка цифра — дрібниця: «жири 41%» нічого не означає.
З ціллю все стає конкретним: «не вистачає 88 г білка на день».

Формули публічні й перевірювані:
  * Базовий обмін — рівняння Міффліна-Сан-Жеора (1990), стандарт у дієтології;
  * Множник активності — класична шкала PAL (1.2–1.9);
  * Корекція під ціль — ±15–20% від добової потреби (безпечний темп 0.5 кг/тиждень);
  * Білок — 1.6–2.2 г/кг для набору й утримання маси при дефіциті
    (позиція ISSN 2017), 0.8 г/кг як мінімум ВООЗ;
  * Жири — не менше 20% енергії (EFSA), решта — вуглеводи.

Нічого з цього не рахує LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

ACTIVITY_FACTORS = {
    "sedentary": 1.2,   # сидяча робота, без тренувань
    "light": 1.375,     # 1–2 тренування на тиждень
    "moderate": 1.55,   # 3–4 тренування
    "high": 1.725,      # 5–6 тренувань
    "athlete": 1.9,     # щоденні тренування або фізична робота
}

GOALS = {
    "lose": {"label": "Схуднути", "kcal_factor": 0.82, "protein_per_kg": 1.8},
    "maintain": {"label": "Тримати вагу", "kcal_factor": 1.0, "protein_per_kg": 1.4},
    "gain": {"label": "Набрати масу", "kcal_factor": 1.15, "protein_per_kg": 2.0},
    "health": {"label": "Просто харчуватись краще", "kcal_factor": 1.0, "protein_per_kg": 1.2},
}

FAT_ENERGY_SHARE = 0.28     # у межах норми EFSA 20–35%
KCAL_PER_G = {"protein": 4.0, "fat": 9.0, "carbs": 4.0}

DEFAULTS = {"weight_kg": 70.0, "height_cm": 172.0, "sex": "male", "age": 30}


def age_from_birthday(birthday: date | str | None) -> int:
    if not birthday:
        return DEFAULTS["age"]
    if isinstance(birthday, str):
        try:
            birthday = date.fromisoformat(birthday[:10])
        except ValueError:
            return DEFAULTS["age"]
    today = date.today()
    return max(
        14, today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
    )


def bmr_mifflin(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """Базовий обмін, ккал/добу. Міффлін-Сан-Жеор."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if str(sex).lower().startswith("m") else -161)


@dataclass
class Targets:
    kcal: int
    protein: int
    fat: int
    carbs: int
    bmr: int
    tdee: int
    goal: str
    goal_label: str
    explanation: str = ""
    assumptions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "kcal": self.kcal, "protein": self.protein, "fat": self.fat, "carbs": self.carbs,
            "bmr": self.bmr, "tdee": self.tdee, "goal": self.goal, "goal_label": self.goal_label,
            "explanation": self.explanation, "assumptions": self.assumptions,
        }


def compute_targets(
    goal: str = "health",
    weight_kg: float | None = None,
    height_cm: float | None = None,
    activity: str = "moderate",
    sex: str | None = None,
    birthday: date | str | None = None,
) -> Targets:
    assumptions: list[str] = []

    if weight_kg is None:
        weight_kg = DEFAULTS["weight_kg"]
        assumptions.append(f"вагу взято усереднену — {weight_kg:.0f} кг")
    if height_cm is None:
        height_cm = DEFAULTS["height_cm"]
        assumptions.append(f"зріст взято усереднений — {height_cm:.0f} см")
    if not sex:
        sex = DEFAULTS["sex"]
        assumptions.append("стать не відома, рахуємо за чоловічою формулою")

    age = age_from_birthday(birthday)
    goal_key = goal if goal in GOALS else "health"
    goal_cfg = GOALS[goal_key]

    bmr = bmr_mifflin(weight_kg, height_cm, age, sex)
    tdee = bmr * ACTIVITY_FACTORS.get(activity, 1.55)
    kcal = tdee * goal_cfg["kcal_factor"]

    protein_g = weight_kg * goal_cfg["protein_per_kg"]
    fat_g = kcal * FAT_ENERGY_SHARE / KCAL_PER_G["fat"]
    carbs_kcal = kcal - protein_g * KCAL_PER_G["protein"] - fat_g * KCAL_PER_G["fat"]
    carbs_g = max(carbs_kcal, 0) / KCAL_PER_G["carbs"]

    return Targets(
        kcal=int(round(kcal)),
        protein=int(round(protein_g)),
        fat=int(round(fat_g)),
        carbs=int(round(carbs_g)),
        bmr=int(round(bmr)),
        tdee=int(round(tdee)),
        goal=goal_key,
        goal_label=goal_cfg["label"],
        explanation=(
            f"Базовий обмін {int(bmr)} ккал (Міффлін-Сан-Жеор), "
            f"з активністю — {int(tdee)} ккал, під ціль «{goal_cfg['label'].lower()}» — "
            f"{int(kcal)} ккал і {int(protein_g)} г білка на день."
        ),
        assumptions=assumptions,
    )


@dataclass
class Gap:
    nutrient: str
    label: str
    target: float
    actual: float
    diff: float          # + = не вистачає, − = надлишок
    severity: str        # ok | low | high
    human: str           # людське пояснення


NUTRIENT_LABELS = {"kcal": "калорії", "protein": "білок", "fat": "жири", "carbs": "вуглеводи"}
UNITS = {"kcal": "ккал", "protein": "г", "fat": "г", "carbs": "г"}


def compare(targets: Targets, per_day: dict[str, float], tolerance: float = 0.12) -> list[Gap]:
    """Порівнює норму з тим, що людина реально КУПУЄ (не їсть) на день."""
    gaps: list[Gap] = []
    target_map = {"kcal": targets.kcal, "protein": targets.protein,
                  "fat": targets.fat, "carbs": targets.carbs}
    for key, target in target_map.items():
        actual = float(per_day.get(key) or 0)
        diff = target - actual
        rel = diff / target if target else 0
        if abs(rel) <= tolerance:
            severity, human = "ok", "у нормі"
        elif rel > 0:
            severity = "low"
            human = f"не вистачає {abs(diff):.0f} {UNITS[key]} на день"
        else:
            severity = "high"
            human = f"перебір на {abs(diff):.0f} {UNITS[key]} на день"
        gaps.append(
            Gap(nutrient=key, label=NUTRIENT_LABELS[key], target=target,
                actual=round(actual, 1), diff=round(diff, 1), severity=severity, human=human)
        )
    return gaps


def gap_to_food(gap: Gap) -> str | None:
    """Переводить дефіцит у зрозумілі продукти — це і є корисна порада."""
    if gap.severity != "low":
        return None
    need = gap.diff
    if gap.nutrient == "protein":
        return (
            f"це приблизно {need / 23 * 100:.0f} г курячого філе "
            f"або {need / 6:.0f} яєць на день"
        )
    if gap.nutrient == "kcal":
        return f"це приблизно {need / 250:.1f} повноцінного прийому їжі"
    if gap.nutrient == "carbs":
        return f"це приблизно {need / 25:.0f} порцій каші або хліба"
    if gap.nutrient == "fat":
        return f"це приблизно {need / 15:.0f} столові ложки олії або горіхів"
    return None
