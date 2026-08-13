"""OpenRouter client.

A pinned model, not `openrouter/auto`. Auto routes by aggregate community spend
on a rolling 7-day window, so a prompt tuned today could be silently reassigned
to a different model tomorrow — unacceptable for a fixed extraction contract.

`require_parameters: true` forces routing to an endpoint that actually honours
`response_format`; without it a provider may treat the schema as a hint. `zdr`
enforces zero data retention at the provider, not just at OpenRouter.
"""

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import ValidationError

from recimin.config import Settings
from recimin.llm.schema import ExtractedRecipe, json_schema

logger = logging.getLogger(__name__)

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = httpx.Timeout(180.0, connect=15.0)
MAX_IMAGES = 12


class LlmUnavailable(Exception):
    """The LLM could not be reached or is disabled."""


class LlmRefused(Exception):
    """The model answered, but not with a usable recipe."""


@dataclass(frozen=True, slots=True)
class Usage:
    """Token accounting, logged so cost stays visible."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


def _image_part(path: Path) -> dict[str, object]:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
    }


def build_payload(
    model: str,
    fallback: str | None,
    system: str,
    text: str,
    images: list[Path],
) -> dict[str, object]:
    """Assemble a chat-completions request."""
    content: list[dict[str, object]] = [{"type": "text", "text": text}]
    content.extend(_image_part(path) for path in images[:MAX_IMAGES])

    payload: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "provider": {"require_parameters": True, "zdr": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "recipe", "strict": True, "schema": json_schema()},
        },
        "temperature": 0,
        "max_tokens": 4000,
    }
    if fallback:
        payload["models"] = [model, fallback]
    return payload


async def extract(
    settings: Settings,
    *,
    system: str,
    text: str,
    images: list[Path] | None = None,
) -> tuple[ExtractedRecipe, Usage]:
    """Ask the model for a recipe and validate what comes back.

    One retry on a validation failure, with the error fed back — OpenRouter's
    Response Healing repairs JSON *syntax* but not schema adherence, so a wrong
    field name arrives looking perfectly well-formed.
    """
    if not settings.llm_enabled or not settings.openrouter_api_key:
        raise LlmUnavailable("LLM extraction is disabled")

    payload = build_payload(
        settings.openrouter_model,
        settings.openrouter_model_fallback,
        system,
        text,
        images or [],
    )
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.allowed_origin,
        "X-Title": "Recimin",
    }

    last_error = ""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for attempt in (1, 2):
            if attempt == 2:
                payload["messages"] = [
                    *payload["messages"],  # type: ignore[misc]
                    {
                        "role": "user",
                        "content": (
                            f"That response did not match the schema: {last_error}. "
                            "Return only valid JSON matching the schema."
                        ),
                    },
                ]

            try:
                response = await client.post(ENDPOINT, json=payload, headers=headers)
            except httpx.HTTPError as error:
                raise LlmUnavailable(f"{type(error).__name__}: {error}") from error

            if response.status_code == 402:
                raise LlmUnavailable("OpenRouter credit exhausted")
            if response.status_code >= 400:
                raise LlmUnavailable(f"HTTP {response.status_code}: {response.text[:200]}")

            body = response.json()
            usage_raw = body.get("usage") or {}
            usage = Usage(
                prompt_tokens=usage_raw.get("prompt_tokens", 0),
                completion_tokens=usage_raw.get("completion_tokens", 0),
            )

            try:
                content = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as error:
                raise LlmRefused(f"malformed response envelope: {error}") from error

            try:
                recipe = ExtractedRecipe.model_validate_json(content)
            except (ValidationError, ValueError) as error:
                last_error = str(error)[:300]
                logger.warning(
                    "llm response failed validation",
                    extra={"attempt": attempt, "error": last_error},
                )
                continue

            logger.info(
                "llm extraction",
                extra={
                    "model": body.get("model"),
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "ingredients": len(recipe.ingredients),
                    "confidence": recipe.confidence,
                },
            )
            return recipe, usage

    raise LlmRefused(f"schema validation failed twice: {last_error}")


def parse_json_response(raw: str) -> dict[str, object]:
    """Best-effort JSON parse, tolerating a markdown fence.

    OpenRouter's Response Healing normally strips these, but it is
    non-streaming only and not every provider routes through it.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return json.loads(text)
