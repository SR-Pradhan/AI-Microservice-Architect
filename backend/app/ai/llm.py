"""The LLM boundary.

Everything above this file talks to `StructuredLLM`, never to the Anthropic SDK directly. That
keeps the Stage Executor testable (inject a fake) and means swapping models or providers touches
exactly one class.
"""

from typing import Any, Protocol

from anthropic import AsyncAnthropic
from pydantic import BaseModel

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
                "ANTHROPIC_API_KEY is not set — add it to backend/.env before running a stage"
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


def get_llm() -> StructuredLLM:
    """FastAPI dependency. Never raises — a missing key surfaces from .generate() instead, so it
    cannot mask a 409 gate error or a 422 path-validation error that should be reported first."""
    settings = get_settings()
    client = (
        AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
    )
    return AnthropicStructuredLLM(
        client=client, model=settings.anthropic_model, max_tokens=settings.anthropic_max_tokens
    )
