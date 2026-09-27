"""LLM access with structured output and a fallback chain: Gemini → Groq → (caller's rule engine).

One call per incident (diagnosis + runbook choice together) to respect free-tier limits.
Every reply is validated against a Pydantic schema; malformed JSON gets one corrective retry.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings

logger = logging.getLogger("opsmind.llm")

REQUEST_TIMEOUT_SECONDS = 45
TEMPERATURE = 0.2
MAX_ATTEMPTS_PER_PROVIDER = 2
HTTP_TOO_MANY_REQUESTS = 429
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMRateLimited(LLMError):
    pass


class Provider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str) -> str: ...


def _raise_for(response: httpx.Response, provider: str) -> None:
    if response.status_code == HTTP_TOO_MANY_REQUESTS:
        raise LLMRateLimited(f"{provider} rate limited (retry-after={response.headers.get('retry-after')})")
    if response.status_code >= httpx.codes.BAD_REQUEST:
        raise LLMError(f"{provider} HTTP {response.status_code}: {response.text[:200]}")


@dataclass
class GeminiProvider:
    api_key: str
    model: str
    transport: httpx.BaseTransport | None = None
    name: str = "gemini"

    def complete_json(self, system: str, user: str) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": TEMPERATURE},
        }
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, transport=self.transport) as client:
            # Key goes in a header, never in the URL (URLs end up in logs).
            response = client.post(GEMINI_URL.format(model=self.model), json=body,
                                   headers={"x-goog-api-key": self.api_key})
        _raise_for(response, self.name)
        try:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"gemini returned no text: {response.text[:200]}") from exc


@dataclass
class GroqProvider:
    api_key: str
    model: str
    transport: httpx.BaseTransport | None = None
    name: str = "groq"

    def complete_json(self, system: str, user: str) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "temperature": TEMPERATURE,
        }
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, transport=self.transport) as client:
            response = client.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
        _raise_for(response, self.name)
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"groq returned no text: {response.text[:200]}") from exc


@dataclass
class LLMResult:
    output: BaseModel
    provider: str
    model: str
    attempts: list[str] = field(default_factory=list)


class LLMClient:
    def __init__(self, providers: list[Provider]) -> None:
        self._providers = providers

    @property
    def is_configured(self) -> bool:
        return bool(self._providers)

    def generate(self, system: str, user: str, schema: type[T]) -> LLMResult:
        attempts: list[str] = []
        for provider in self._providers:
            prompt = user
            for _ in range(MAX_ATTEMPTS_PER_PROVIDER):
                try:
                    raw = _FENCE.sub("", provider.complete_json(system, prompt).strip())
                    output = schema.model_validate_json(raw)
                    attempts.append(f"{provider.name}: ok")
                    return LLMResult(output, provider.name, provider.model, attempts)
                except ValidationError as exc:
                    attempts.append(f"{provider.name}: malformed output ({exc.error_count()} errors)")
                    prompt = f"{user}\n\nYour previous reply was invalid: {exc.errors()[:3]}. Return ONLY valid JSON."
                except (LLMError, httpx.HTTPError) as exc:
                    attempts.append(f"{provider.name}: {exc}")
                    break
        logger.warning("all LLM providers failed", extra={"event": "llm_failed", "attempts": attempts})
        raise LLMError("; ".join(attempts) or "no LLM provider configured")


def build_llm(settings: Settings) -> LLMClient:
    providers: list[Provider] = []
    if settings.gemini_api_key:
        providers.append(GeminiProvider(settings.gemini_api_key, settings.gemini_model))
    if settings.groq_api_key:
        providers.append(GroqProvider(settings.groq_api_key, settings.groq_model))
    return LLMClient(providers)
