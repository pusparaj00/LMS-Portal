"""The one place the LLM is called (TR-A-04). Provider, model, timeout, retries and temperature come
from configuration; swapping provider needs no change elsewhere."""
import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings

log = logging.getLogger("app.llm")
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
BACKOFF_SECONDS = 1.5
MAX_PROVIDER_WAIT_SECONDS = 90  # a per-minute limit is worth waiting for; a per-day limit is not
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _provider_retry_delay(response: httpx.Response) -> float | None:
    """Seconds the provider asks us to wait (its RetryInfo detail), if it said."""
    try:
        for detail in response.json()["error"]["details"]:
            if "retryDelay" in detail:
                return float(str(detail["retryDelay"]).rstrip("s"))
    except (KeyError, ValueError, TypeError):
        return None
    return None


def _is_billing_error(response: httpx.Response) -> bool:
    """A 429 that means the account has no credit or quota left: retrying cannot help."""
    try:
        error = response.json()["error"]
        code = f"{error.get('code', '')} {error.get('type', '')} {error.get('message', '')}".lower()
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return any(word in code for word in ("insufficient_quota", "billing", "exceeded your current quota"))


class LLMError(Exception):
    """The model could not be reached or returned nothing usable."""


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    timeout_s: float
    max_retries: int
    temperature: float
    thinking_budget: int = 0


class LLMAdapter(Protocol):
    config: LLMConfig

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> str: ...


class StubAdapter:
    """Canned reply, for tests and for running without a key."""

    reply = "This is a canned reply from the stub LLM adapter."

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> str:
        return self.reply


class GeminiAdapter:
    def __init__(self, config: LLMConfig, api_key: str) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self.config = config
        self._api_key = api_key

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> str:
        generation: dict = {"temperature": self.config.temperature}
        if self.config.thinking_budget > 0:
            generation["thinkingConfig"] = {"thinkingBudget": self.config.thinking_budget}
        if json_schema is not None:
            generation["responseMimeType"] = "application/json"
            generation["responseSchema"] = json_schema
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation,
        }
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            started = time.perf_counter()
            try:
                response = httpx.post(
                    GEMINI_URL.format(model=self.config.model),
                    json=body,
                    headers={"x-goog-api-key": self._api_key},
                    timeout=self.config.timeout_s,
                )
                response.raise_for_status()
                parts = response.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts)
                if text.strip():
                    log.info(
                        "llm call",
                        extra={"fields": {"model": self.config.model, "attempt": attempt,
                                          "ms": round((time.perf_counter() - started) * 1000)}},
                    )
                    return text
                last_error = LLMError("the model returned no text")
            except httpx.HTTPStatusError as exc:
                last_error = LLMError(f"HTTP {exc.response.status_code} from the model")
                if exc.response.status_code not in TRANSIENT_STATUS:
                    break  # a rejected request will not succeed on retry
                wait = _provider_retry_delay(exc.response)
                if wait is not None and wait > MAX_PROVIDER_WAIT_SECONDS:
                    break  # quota used up for the day: waiting is pointless
                if wait is not None and attempt < self.config.max_retries:
                    time.sleep(wait)
                    continue
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                # Never include the request: its headers carry the key.
                last_error = LLMError(f"{type(exc).__name__}: {str(exc)[:120]}".replace(self._api_key, "<key>"))
            if attempt < self.config.max_retries:
                time.sleep(BACKOFF_SECONDS * (attempt + 1))
        raise last_error or LLMError("LLM call failed")


OPENAI_COMPATIBLE = {
    "groq": ("https://api.groq.com/openai/v1", "groqcloud_api_key", "llm_model_groq"),
    "deepseek": ("https://api.deepseek.com", "deepseek_api_key", "llm_model_deepseek"),
    "openai": ("https://api.openai.com/v1", "openai_api_key", "llm_model_openai"),
    "mistral": ("https://api.mistral.ai/v1", "mistral_api_key", "llm_model_mistral"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter_api_key", "llm_model_openrouter"),
}


class OpenAICompatibleAdapter:
    """Chat-completions API shared by OpenAI, Groq and DeepSeek."""

    def __init__(self, config: LLMConfig, api_key: str, base_url: str) -> None:
        if not api_key:
            raise LLMError(f"no API key for {config.provider}")
        self.config = config
        self._api_key = api_key
        self._url = f"{base_url}/chat/completions"

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> str:
        if json_schema is not None:
            system += "\n\nReply with one JSON object matching this JSON schema:\n" + json.dumps(json_schema)
        body: dict = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_schema is not None:
            body["response_format"] = {"type": "json_object"}
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            started = time.perf_counter()
            try:
                response = httpx.post(
                    self._url, json=body, headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=self.config.timeout_s,
                )
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"] or ""
                if text.strip():
                    log.info(
                        "llm call",
                        extra={"fields": {"provider": self.config.provider, "model": self.config.model,
                                          "attempt": attempt, "ms": round((time.perf_counter() - started) * 1000)}},
                    )
                    return text
                last_error = LLMError("the model returned no text")
            except httpx.HTTPStatusError as exc:
                last_error = LLMError(f"HTTP {exc.response.status_code} from {self.config.provider}")
                if exc.response.status_code not in TRANSIENT_STATUS or _is_billing_error(exc.response):
                    break
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_error = LLMError(f"{type(exc).__name__}: {str(exc)[:120]}".replace(self._api_key, "<key>"))
            if attempt < self.config.max_retries:
                time.sleep(BACKOFF_SECONDS * (attempt + 1))
        raise last_error or LLMError("LLM call failed")


class FallbackChain:
    """Tries each provider in order; the next one is used when one fails or has no quota left."""

    def __init__(self, adapters: list[LLMAdapter]) -> None:
        self.adapters = adapters
        self.last: LLMAdapter = adapters[0]

    @property
    def config(self) -> LLMConfig:
        """The provider that answered last (or the first, before any call)."""
        return self.last.config

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> str:
        errors = []
        for adapter in self.adapters:
            try:
                reply = adapter.complete(system, user, json_schema)
            except LLMError as exc:
                errors.append(f"{adapter.config.provider}: {exc}")
                log.warning("provider failed, trying the next", extra={"fields": {"provider": adapter.config.provider}})
                continue
            self.last = adapter
            return reply
        raise LLMError("every provider failed: " + "; ".join(errors))


def build_adapter(settings: Settings) -> LLMAdapter:
    def config(provider: str, model: str) -> LLMConfig:
        return LLMConfig(
            provider=provider, model=model, timeout_s=settings.llm_timeout_s, max_retries=settings.llm_max_retries,
            temperature=settings.llm_temperature, thinking_budget=settings.llm_thinking_budget,
        )

    primary_config = config(settings.llm_provider, settings.llm_model)
    if primary_config.provider == "stub":
        return StubAdapter(primary_config)
    if primary_config.provider == "gemini":
        adapters: list[LLMAdapter] = [GeminiAdapter(primary_config, settings.gemini_api_key)]
    elif primary_config.provider in OPENAI_COMPATIBLE:
        adapters = [_compatible(settings, primary_config.provider, config)]
    else:
        raise ValueError(f"unsupported LLM_PROVIDER: {primary_config.provider}")
    for name in (n.strip() for n in settings.llm_fallback.split(",") if n.strip()):
        if name not in OPENAI_COMPATIBLE:
            raise ValueError(f"unsupported fallback provider: {name}")
        try:
            adapters.append(_compatible(settings, name, config))
        except LLMError:
            log.warning("fallback provider skipped: no key", extra={"fields": {"provider": name}})
    return adapters[0] if len(adapters) == 1 else FallbackChain(adapters)


def _compatible(settings: Settings, provider: str, make_config) -> OpenAICompatibleAdapter:
    base_url, key_field, model_field = OPENAI_COMPATIBLE[provider]
    return OpenAICompatibleAdapter(
        make_config(provider, getattr(settings, model_field)), getattr(settings, key_field), base_url
    )
