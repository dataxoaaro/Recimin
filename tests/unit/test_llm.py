"""LLM client, schema and extraction wiring.

No network. The provider contract is asserted on the request we build and the
responses we tolerate, because those are the parts we control.
"""

import json
from pathlib import Path

import httpx
import pytest

from recimin.config import Settings
from recimin.llm import client, prompts
from recimin.llm.extract import to_normalised
from recimin.llm.schema import CATEGORY_KEYS, ExtractedRecipe, json_schema

SETTINGS = Settings(
    jwt_secret="x" * 32,
    site_password="site-password",
    openrouter_api_key="test-key",
    openrouter_model="google/gemini-3.1-flash-lite",
    openrouter_model_fallback="qwen/qwen3-vl-32b-instruct",
)

VALID = {
    "title": "Kinder-juustokakku",
    "language": "fi",
    "category": "cake",
    "servings": 12,
    "yield_text": None,
    "total_time_minutes": 240,
    "tags": ["party"],
    "ingredients": [
        {"raw_text": "200 g Kinder-suklaata", "qty": 200, "unit": "g", "item": "Kinder-suklaata"},
        {"raw_text": "2 dl kermaa", "qty": 2, "unit": "dl", "item": "kermaa"},
    ],
    "instructions_md": "1. Sulata suklaa\n2. Vatkaa kerma",
    "confidence": "high",
}


def _mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """Route the client's requests to a handler.

    The real AsyncClient must be captured before patching: a lambda that calls
    httpx.AsyncClient after replacing that name calls itself forever.
    """
    real = httpx.AsyncClient
    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        lambda **kwargs: real(transport=httpx.MockTransport(handler)),
    )


def _response(payload: dict[str, object], *, status: int = 200) -> httpx.Response:
    body = {
        "model": "google/gemini-3.1-flash-lite",
        "usage": {"prompt_tokens": 4200, "completion_tokens": 350},
        "choices": [{"message": {"content": json.dumps(payload)}}],
    }
    return httpx.Response(status, json=body)


# ─── the request contract ────────────────────────────────────────────────


def test_payload_pins_the_model_and_lists_a_fallback() -> None:
    """openrouter/auto routes by community spend on a 7-day window.

    A fixed extraction contract cannot tolerate being silently reassigned.
    """
    payload = client.build_payload("model-a", "model-b", "sys", "text", [])
    assert payload["model"] == "model-a"
    assert payload["models"] == ["model-a", "model-b"]
    assert "auto" not in str(payload["model"])


def test_payload_requires_a_schema_honouring_endpoint() -> None:
    """Structured-output support is per endpoint, not per model."""
    payload = client.build_payload("m", None, "sys", "text", [])
    assert payload["provider"] == {"require_parameters": True, "zdr": True}
    assert payload["response_format"]["type"] == "json_schema"  # type: ignore[index]
    assert payload["response_format"]["json_schema"]["strict"] is True  # type: ignore[index]


def test_payload_is_deterministic() -> None:
    assert client.build_payload("m", None, "s", "t", [])["temperature"] == 0


def test_images_are_capped(tmp_path: Path) -> None:
    """More frames is not better: 8->16 bought +0.26% at 1.6x latency."""
    images = []
    for index in range(20):
        path = tmp_path / f"f{index}.jpg"
        path.write_bytes(b"\xff\xd8\xff\xd9")
        images.append(path)

    payload = client.build_payload("m", None, "sys", "text", images)
    content = payload["messages"][1]["content"]  # type: ignore[index]
    image_parts = [part for part in content if part["type"] == "image_url"]  # type: ignore[index]
    assert len(image_parts) == client.MAX_IMAGES


def test_the_schema_has_no_regex_patterns() -> None:
    """OpenAI rejects `pattern` in structured outputs."""
    assert "pattern" not in json.dumps(json_schema())


def test_the_schema_category_enum_matches_the_database() -> None:
    categories = json_schema()["properties"]["category"]["enum"]  # type: ignore[index]
    assert categories == CATEGORY_KEYS


# ─── responses ───────────────────────────────────────────────────────────


async def test_valid_response_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return _response(VALID)

    _mock_transport(monkeypatch, handler)
    recipe, usage = await client.extract(SETTINGS, system="s", text="t")
    assert recipe.title == "Kinder-juustokakku"
    assert recipe.confidence == "high"
    assert usage.prompt_tokens == 4200


async def test_a_schema_violation_is_retried_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Response Healing repairs JSON syntax, not schema adherence.

    A wrong field name arrives perfectly well-formed, so client-side validation
    is the actual guarantee.
    """
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _response({"title": "Broken", "language": "klingon"})
        return _response(VALID)

    _mock_transport(monkeypatch, handler)
    recipe, _ = await client.extract(SETTINGS, system="s", text="t")
    assert calls == 2
    assert recipe.title == "Kinder-juustokakku"


async def test_two_failures_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return _response({"nonsense": True})

    _mock_transport(monkeypatch, handler)
    with pytest.raises(client.LlmRefused):
        await client.extract(SETTINGS, system="s", text="t")


async def test_exhausted_credit_is_named_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": "insufficient credits"})

    _mock_transport(monkeypatch, handler)
    with pytest.raises(client.LlmUnavailable, match="credit"):
        await client.extract(SETTINGS, system="s", text="t")


async def test_a_disabled_llm_never_calls_out() -> None:
    disabled = SETTINGS.model_copy(update={"llm_enabled": False})
    with pytest.raises(client.LlmUnavailable, match="disabled"):
        await client.extract(disabled, system="s", text="t")


async def test_a_missing_api_key_never_calls_out() -> None:
    keyless = SETTINGS.model_copy(update={"openrouter_api_key": ""})
    with pytest.raises(client.LlmUnavailable):
        await client.extract(keyless, system="s", text="t")


def test_markdown_fences_are_tolerated() -> None:
    assert client.parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert client.parse_json_response('{"a": 1}') == {"a": 1}


# ─── conversion ──────────────────────────────────────────────────────────


def test_alternatives_are_re_derived_not_trusted() -> None:
    """The TAI suffix is deterministic; a rule beats hoping the model noticed."""
    extracted = ExtractedRecipe(
        title="Mansikkakakku",
        language="fi",
        category="cake",
        ingredients=[
            {"raw_text": "5 munan sokerikakkupohja TAI"},  # type: ignore[list-item]
            {"raw_text": "5 munan gluteeniton kakkupohja"},  # type: ignore[list-item]
            {"raw_text": "2 dl kermaa"},  # type: ignore[list-item]
        ],
        instructions_md="1. Bake",
    )
    _, rows = to_normalised(extracted)
    assert rows[1]["alternative_of"] == 0
    assert rows[2]["alternative_of"] is None


def test_the_deterministic_parser_fills_gaps_the_model_left() -> None:
    extracted = ExtractedRecipe(
        title="X",
        language="fi",
        category="cake",
        ingredients=[{"raw_text": "1½ dl kermaa"}],  # type: ignore[list-item]
        instructions_md="",
    )
    _, rows = to_normalised(extracted)
    # The model returned no qty; the fallback parser must not read 1½ as 5.5.
    assert rows[0]["qty"] == 1.5
    assert rows[0]["unit"] == "dl"


def test_raw_text_always_survives_conversion() -> None:
    extracted = ExtractedRecipe(
        title="X",
        language="en",
        category="cake",
        ingredients=[{"raw_text": "a pinch of salt"}],  # type: ignore[list-item]
        instructions_md="",
    )
    recipe, rows = to_normalised(extracted)
    assert recipe.ingredients == ["a pinch of salt"]
    assert rows[0]["raw_text"] == "a pinch of salt"


# ─── prompts ─────────────────────────────────────────────────────────────


def test_prompts_state_the_finnish_unit_rule() -> None:
    """tl is 5ml, not a US tsp. Getting this wrong is a silent error."""
    assert "tl is 5 ml" in prompts.SOCIAL_EXTRACTION
    assert "rkl is 15 ml" in prompts.SOCIAL_EXTRACTION


def test_prompts_tell_the_model_where_quantities_actually_live() -> None:
    assert "on-screen text" in prompts.SOCIAL_EXTRACTION


def test_prompts_forbid_inventing_categories() -> None:
    for key in ("main_course", "cake", "bread"):
        assert key in prompts.SOCIAL_EXTRACTION
