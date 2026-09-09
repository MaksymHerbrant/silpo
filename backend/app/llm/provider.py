"""Єдиний інтерфейс до LLM: Gemini або Claude, перемикання через .env.

Навіщо абстракція: числа в застосунку рахує детермінований код, а модель лише
планує послідовність дій і формулює текст. Тому провайдер — змінна деталь,
а не архітектурне рішення, і його треба вміти замінити однією змінною.

    LLM_PROVIDER=gemini   GEMINI_API_KEY=...
    LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=...
    LLM_PROVIDER=none     -> усе працює на правилах, без LLM

Обидва провайдери підтримують tool-use, тому агент однаковий для обох.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

import httpx

from app.config import get_settings

log = logging.getLogger("llm")


@dataclass
class ToolSpec:
    """Опис інструмента у нейтральному вигляді (JSON Schema)."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]


@dataclass
class Step:
    """Один крок агента — для трасування в UI і в /debug/mcp-log."""

    kind: str            # think | tool | answer
    text: str = ""
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    result_preview: str = ""


class LLMUnavailable(RuntimeError):
    pass


class BaseProvider:
    name = "none"

    async def complete(self, system: str, prompt: str, max_tokens: int = 500) -> str:
        raise LLMUnavailable("LLM не налаштований")

    async def run_agent(
        self, system: str, prompt: str, tools: list[ToolSpec], max_steps: int = 12
    ) -> tuple[str, list[Step]]:
        raise LLMUnavailable("LLM не налаштований")


# --------------------------------------------------------------------------- #
class GeminiProvider(BaseProvider):
    """Google Gemini через REST — без SDK, щоб не тягнути ще одну залежність."""

    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.BASE}/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(url, params={"key": self.api_key}, json=payload)
        if r.status_code == 429:
            raise LLMUnavailable("Gemini: вичерпано безкоштовний ліміт запитів")
        if r.status_code >= 400:
            raise LLMUnavailable(f"Gemini {r.status_code}: {r.text[:300]}")
        return r.json()

    @staticmethod
    def _text_of(candidate: dict[str, Any]) -> str:
        parts = (candidate.get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts).strip()

    async def complete(self, system: str, prompt: str, max_tokens: int = 500) -> str:
        data = await self._post({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.4},
        })
        candidates = data.get("candidates") or []
        return self._text_of(candidates[0]) if candidates else ""

    async def run_agent(
        self, system: str, prompt: str, tools: list[ToolSpec], max_steps: int = 12
    ) -> tuple[str, list[Step]]:
        registry = {t.name: t for t in tools}
        declarations = [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools
        ]
        contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": prompt}]}]
        steps: list[Step] = []

        for _ in range(max_steps):
            data = await self._post({
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": contents,
                "tools": [{"functionDeclarations": declarations}],
                "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.3},
            })
            candidates = data.get("candidates") or []
            if not candidates:
                break
            parts = (candidates[0].get("content") or {}).get("parts") or []
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            text = "".join(p.get("text", "") for p in parts).strip()

            if not calls:
                if text:
                    steps.append(Step(kind="answer", text=text))
                return text, steps

            if text:
                steps.append(Step(kind="think", text=text))
            contents.append({"role": "model", "parts": parts})

            responses = []
            for call in calls:
                name = call.get("name", "")
                args = call.get("args") or {}
                tool = registry.get(name)
                if tool is None:
                    result: Any = {"error": f"невідомий інструмент {name}"}
                else:
                    try:
                        result = await tool.handler(**args)
                    except Exception as exc:  # noqa: BLE001
                        result = {"error": str(exc)[:300]}
                steps.append(Step(
                    kind="tool", tool=name, args=args,
                    result_preview=json.dumps(result, ensure_ascii=False)[:300],
                ))
                responses.append({"functionResponse": {"name": name, "response": {"result": result}}})
            contents.append({"role": "user", "parts": responses})

        return "Не вдалось завершити за відведену кількість кроків.", steps


# --------------------------------------------------------------------------- #
class AnthropicProvider(BaseProvider):
    """Claude через офіційний SDK. Запасний варіант і швидка заміна на демо."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def complete(self, system: str, prompt: str, max_tokens: int = 500) -> str:
        resp = await self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    async def run_agent(
        self, system: str, prompt: str, tools: list[ToolSpec], max_steps: int = 12
    ) -> tuple[str, list[Step]]:
        registry = {t.name: t for t in tools}
        schema = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        steps: list[Step] = []

        for _ in range(max_steps):
            resp = await self.client.messages.create(
                model=self.model, max_tokens=4096, system=system,
                tools=schema, messages=messages,
            )
            tool_uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            ).strip()

            if not tool_uses:
                if text:
                    steps.append(Step(kind="answer", text=text))
                return text, steps

            if text:
                steps.append(Step(kind="think", text=text))
            messages.append({"role": "assistant", "content": resp.content})

            results = []
            for block in tool_uses:
                tool = registry.get(block.name)
                if tool is None:
                    result: Any = {"error": f"невідомий інструмент {block.name}"}
                else:
                    try:
                        result = await tool.handler(**(block.input or {}))
                    except Exception as exc:  # noqa: BLE001
                        result = {"error": str(exc)[:300]}
                steps.append(Step(
                    kind="tool", tool=block.name, args=dict(block.input or {}),
                    result_preview=json.dumps(result, ensure_ascii=False)[:300],
                ))
                results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False)[:20000],
                })
            messages.append({"role": "user", "content": results})

        return "Не вдалось завершити за відведену кількість кроків.", steps


# --------------------------------------------------------------------------- #
_provider: BaseProvider | None = None


def get_provider() -> BaseProvider:
    """Повертає активний провайдер. Якщо ключа немає — заглушка без LLM."""
    global _provider
    if _provider is not None:
        return _provider

    s = get_settings()
    choice = (s.llm_provider or "none").lower()

    if choice == "gemini" and s.gemini_api_key:
        _provider = GeminiProvider(s.gemini_api_key, s.gemini_model)
    elif choice == "anthropic" and s.anthropic_api_key:
        _provider = AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
    elif s.gemini_api_key:
        _provider = GeminiProvider(s.gemini_api_key, s.gemini_model)
    elif s.anthropic_api_key:
        _provider = AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
    else:
        _provider = BaseProvider()

    log.info("LLM-провайдер: %s", _provider.name)
    return _provider


def reset_provider() -> None:
    global _provider
    _provider = None
