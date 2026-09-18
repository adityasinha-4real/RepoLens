"""Optional AI providers behind one small interface.

RepoLens works fully without AI. A provider is only built when AI_PROVIDER is configured.
Supported:
    anthropic - Claude via the official Anthropic SDK (`pip install -e ".[ai]"`)
    openai    - any OpenAI-compatible chat-completions endpoint (OpenAI, Groq, OpenRouter,
                a local Ollama/LM Studio server, ...) over plain HTTP
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import AIUnavailableError

logger = logging.getLogger(__name__)

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class Completion:
    text: str
    model: str


class AIProvider(Protocol):
    name: str
    model: str

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> Completion: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str | None, timeout: float) -> None:
        try:
            import anthropic  # optional dependency
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise AIUnavailableError(
                'AI_PROVIDER=anthropic requires the optional dependency: pip install -e ".[ai]"'
            ) from exc
        self._anthropic = anthropic
        self.model = model or DEFAULT_ANTHROPIC_MODEL
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> Completion:
        a = self._anthropic
        try:
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": schema},
                },
                # Server-side refusal fallbacks: a declined request is retried on Anthropic's
                # recommended fallback model instead of failing.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except a.AuthenticationError as exc:
            logger.error("Anthropic rejected the configured API key")
            raise AIUnavailableError("The AI provider rejected the server's credentials.") from exc
        except a.RateLimitError as exc:
            raise AIUnavailableError(
                "The AI provider is rate limiting requests. Try later."
            ) from exc
        except a.BadRequestError as exc:
            logger.warning("Anthropic bad request: %s", exc.message)
            raise AIUnavailableError("The AI provider rejected the request.") from exc
        except a.APIStatusError as exc:
            logger.warning("Anthropic error %s", exc.status_code)
            raise AIUnavailableError("The AI provider returned an error. Try later.") from exc
        except a.APIConnectionError as exc:
            raise AIUnavailableError("Could not reach the AI provider.") from exc

        if response.stop_reason == "refusal":
            raise AIUnavailableError("The AI provider declined to summarize this repository.")
        if response.stop_reason == "max_tokens":
            raise AIUnavailableError("The AI summary was cut off; try again.")
        text = "".join(b.text for b in response.content if b.type == "text")
        return Completion(text=text, model=response.model)


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str | None,
        http: httpx.AsyncClient,
        timeout: float,
    ) -> None:
        self.model = model
        self._url = f"{(base_url or DEFAULT_OPENAI_BASE_URL).rstrip('/')}/chat/completions"
        self._key = api_key
        self._http = http
        self._timeout = timeout

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> Completion:
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": f"{system}\n\nReturn only a JSON object matching "
                    f"this JSON Schema:\n{json.dumps(schema)}",
                },
                {"role": "user", "content": user},
            ],
        }
        try:
            response = await self._http.post(
                self._url, json=body, headers=headers, timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise AIUnavailableError("Could not reach the AI provider.") from exc
        if response.status_code in (401, 403):
            raise AIUnavailableError("The AI provider rejected the server's credentials.")
        if response.status_code == 429:
            raise AIUnavailableError("The AI provider is rate limiting requests. Try later.")
        if response.status_code >= 400:
            logger.warning("AI provider returned HTTP %s", response.status_code)
            raise AIUnavailableError("The AI provider returned an error. Try later.")
        try:
            data = response.json()
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIUnavailableError("The AI provider returned a malformed response.") from exc
        if choice.get("finish_reason") == "length":
            raise AIUnavailableError("The AI summary was cut off; try again.")
        return Completion(text=text or "", model=str(data.get("model") or self.model))


def build_provider(settings: Settings, http: httpx.AsyncClient) -> AIProvider | None:
    """Return the configured provider, or None when AI is disabled."""
    provider = (settings.ai_provider or "").strip().lower()
    if not provider:
        return None
    key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else None
    if provider == "anthropic":
        if not key:
            raise AIUnavailableError("AI_PROVIDER=anthropic requires AI_API_KEY.")
        return AnthropicProvider(key, settings.ai_model, settings.ai_timeout_seconds)
    if provider in ("openai", "openai-compatible"):
        if not settings.ai_model:
            raise AIUnavailableError("AI_PROVIDER=openai requires AI_MODEL.")
        return OpenAICompatibleProvider(
            key, settings.ai_model, settings.ai_base_url, http, settings.ai_timeout_seconds
        )
    raise AIUnavailableError(f"Unsupported AI_PROVIDER '{provider[:40]}'.")
