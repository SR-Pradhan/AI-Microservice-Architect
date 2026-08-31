"""The LLM boundary: provider selection, message mapping, and validation of provider output."""

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.ai.contracts import BoundariesOutput
from app.ai.llm import (
    AnthropicStructuredLLM,
    GeminiStructuredLLM,
    MissingAPIKeyError,
    get_llm,
)
from app.core.config import get_settings

VALID = {
    "services": [
        {"name": "A", "responsibility": "x", "domain": "d", "key_entities": []},
        {"name": "B", "responsibility": "y", "domain": "d", "key_entities": []},
    ],
    "boundaries_rationale": "r",
}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Settings are cached; each test that changes env must start from a clean cache."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_provider_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    assert isinstance(get_llm(), GeminiStructuredLLM)

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    assert isinstance(get_llm(), AnthropicStructuredLLM)


@pytest.mark.asyncio
async def test_missing_key_raises_at_call_time_not_construction() -> None:
    """Construction must always succeed, so a config error cannot mask a workflow error."""
    for llm in (
        GeminiStructuredLLM(client=None, model="m"),
        AnthropicStructuredLLM(client=None, model="m", max_tokens=1),
    ):
        with pytest.raises(MissingAPIKeyError):
            await llm.generate(system="s", messages=[], output_format=BoundariesOutput)


class _FakeResponse:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.candidates: list[Any] = []


class _FakeGeminiClient:
    """Captures the request so the message mapping can be asserted."""

    def __init__(self, text: str | None) -> None:
        self._text = text
        self.captured: dict[str, Any] = {}
        outer = self

        class _Models:
            async def generate_content(self, *, model, contents, config):
                outer.captured = {"model": model, "contents": contents, "config": config}
                return _FakeResponse(outer._text)

        class _Aio:
            models = _Models()

        self.aio = _Aio()


@pytest.mark.asyncio
async def test_gemini_maps_roles_and_passes_schema() -> None:
    import json

    client = _FakeGeminiClient(json.dumps(VALID))
    llm = GeminiStructuredLLM(client=client, model="gemini-test")  # type: ignore[arg-type]

    result = await llm.generate(
        system="be an architect",
        messages=[
            {"role": "user", "content": "design it"},
            {"role": "assistant", "content": "here you go"},
            {"role": "user", "content": "fix it"},
        ],
        output_format=BoundariesOutput,
    )

    assert isinstance(result, BoundariesOutput)
    # Anthropic's "assistant" must become Gemini's "model", or the conversation is rejected.
    assert [c.role for c in client.captured["contents"]] == ["user", "model", "user"]
    assert client.captured["config"].system_instruction == "be an architect"
    assert client.captured["config"].response_schema is BoundariesOutput


@pytest.mark.asyncio
async def test_gemini_output_is_validated_against_our_contract() -> None:
    """Gemini does not enforce constraints like min_length server-side, so we must."""
    import json

    one_service = {**VALID, "services": VALID["services"][:1]}
    llm = GeminiStructuredLLM(client=_FakeGeminiClient(json.dumps(one_service)), model="m")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        await llm.generate(system="s", messages=[], output_format=BoundariesOutput)


@pytest.mark.asyncio
async def test_gemini_empty_response_is_a_retryable_error() -> None:
    llm = GeminiStructuredLLM(client=_FakeGeminiClient(None), model="m")  # type: ignore[arg-type]
    # ValueError is what the Stage Executor's retry loop catches.
    with pytest.raises(ValueError, match="no content"):
        await llm.generate(system="s", messages=[], output_format=BoundariesOutput)
