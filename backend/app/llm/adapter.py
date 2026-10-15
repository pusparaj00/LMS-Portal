"""The one place the LLM is called (TR-A-04). Provider, model, timeout, retries and temperature come
from configuration; swapping provider needs no change elsewhere."""
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


def build_adapter(settings: Settings) -> LLMAdapter:
    config = LLMConfig(
        provider=settings.llm_provider,
        model=settings.llm_model,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        temperature=settings.llm_temperature,
        thinking_budget=settings.llm_thinking_budget,
    )
    if config.provider == "stub":
        return StubAdapter(config)
    if config.provider == "gemini":
        return GeminiAdapter(config, settings.gemini_api_key)
    raise ValueError(f"unsupported LLM_PROVIDER: {config.provider}")
