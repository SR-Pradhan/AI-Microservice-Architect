"""The LLM boundary.

Everything above this file talks to `StructuredLLM`, never to a vendor SDK. That keeps the Stage
Executor testable (inject a fake), and means supporting a second provider costs one class here and
nothing anywhere else.

Two providers ship today:
  * anthropic — Claude, via `client.messages.parse()`
  * gemini    — Google Gemini, via `response_schema` structured output (has a free tier)

Both are given the same Pydantic contract and both return a validated instance of it.
"""

import json
from typing import Any, Protocol

from anthropic import AsyncAnthropic
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel

from app.ai.gemini_schema import to_gemini_schema
from app.core.config import get_settings


class MissingAPIKeyError(RuntimeError):
    """Raised at call time, not construction time, so config errors never mask workflow errors."""


class StructuredLLM(Protocol):
    """Anything that can turn a prompt into an instance of a Pydantic model."""

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        output_format: type[BaseModel],
    ) -> BaseModel: ...


class AnthropicStructuredLLM:
    """Claude, in structured-output mode. Never freeform text that we then try to parse."""

    def __init__(self, client: AsyncAnthropic | None, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        output_format: type[BaseModel],
    ) -> BaseModel:
        if self._client is None:
            raise MissingAPIKeyError(
                "ANTHROPIC_API_KEY is not set — add it to backend/.env, or set "
                "LLM_PROVIDER=gemini to use the free tier instead"
            )
        # messages.parse() sends the model our Pydantic schema as a hard output constraint and
        # returns an already-validated instance in .parsed_output.
        response = await self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
            output_format=output_format,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError("Model returned no parseable structured output")
        return parsed


class GeminiStructuredLLM:
    """Google Gemini, using response_schema for constrained JSON output.

    Gemini's schema support is a subset of JSON Schema, so the Pydantic schema is translated before
    it is sent (see gemini_schema.py) and the response is validated against the real Pydantic model
    afterwards. That second step both enforces the dropped constraints and produces a
    ValidationError the retry loop can feed back.
    """

    # Gemini uses "model" where Anthropic uses "assistant"; every other role name matches.
    _ROLE_MAP = {"assistant": "model", "user": "user"}

    def __init__(self, client: genai.Client | None, model: str) -> None:
        self._client = client
        self._model = model

    def _to_contents(self, messages: list[dict[str, Any]]) -> list[genai_types.Content]:
        return [
            genai_types.Content(
                role=self._ROLE_MAP.get(m["role"], "user"),
                parts=[genai_types.Part(text=str(m["content"]))],
            )
            for m in messages
        ]

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        output_format: type[BaseModel],
    ) -> BaseModel:
        if self._client is None:
            raise MissingAPIKeyError(
                "GEMINI_API_KEY is not set — get a free key from https://aistudio.google.com/apikey "
                "and add it to backend/.env"
            )
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._to_contents(messages),
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=to_gemini_schema(output_format.model_json_schema()),
            ),
        )
        text = response.text
        if not text:
            # Usually a safety block or an empty candidate; surface why rather than a bare None.
            raise ValueError(f"Gemini returned no content (finish reason: {_finish_reason(response)})")
        # model_validate_json raises ValidationError, which the Stage Executor retries with feedback.
        return output_format.model_validate_json(text)


def _finish_reason(response: Any) -> str:
    try:
        return str(response.candidates[0].finish_reason)
    except (AttributeError, IndexError, TypeError):
        return "unknown"


def get_llm() -> StructuredLLM:
    """FastAPI dependency. Never raises — a missing key surfaces from .generate() instead, so it
    cannot mask a 409 gate error or a 422 path-validation error that should be reported first."""
    settings = get_settings()

    if settings.llm_provider == "gemini":
        client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
        return GeminiStructuredLLM(client=client, model=settings.gemini_model)

    client = (
        AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
    )
    return AnthropicStructuredLLM(
        client=client, model=settings.anthropic_model, max_tokens=settings.anthropic_max_tokens
    )
