"""The one place the LLM is called (TR-A-04). Provider, model, timeout, retries and temperature come
from configuration; swapping provider needs no change elsewhere."""
import json
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings

log = logging.getLogger("app.llm")
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
BACKOFF_SECONDS = 1.5
MAX_PROVIDER_WAIT_SECONDS = 90  # a per-minute limit is worth waiting for; a per-day limit is not
MIN_USEFUL_SECONDS = 1.0  # a call with less time left than this cannot finish
PERMANENT_STATUS = {401, 403, 404}  # bad key, project denied, model gone: retrying soon cannot help
REJECTED_COOLDOWN_SECONDS = 600
QUOTA_COOLDOWN_SECONDS = 60  # when the provider does not say how long to wait
UNREACHABLE_COOLDOWN_SECONDS = 60  # nothing listens there (a local model that is not running): do not retry per request
SLOW_COOLDOWN_SECONDS = 30  # a provider that spent its whole share of the budget goes behind the others for a while
MAX_SHARE_DIVISOR = 3  # the first provider may use at most a third of the budget, so the others still get a turn
# provider and model -> time.monotonic() until which it goes to the back of the chain
_cooling: dict[tuple[str, str], float] = {}
# How many model calls may be in flight at once, shared by every request in this process (Settings.llm_max_concurrent).
_slots_lock = threading.Lock()
_slots: tuple[int, threading.BoundedSemaphore] | None = None
# The moment (time.monotonic) by which the whole chain must have answered; set by FallbackChain.
_deadline: ContextVar[float | None] = ContextVar("llm_deadline", default=None)
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
    """The model could not be reached or returned nothing usable.

    `cooldown_s` > 0 says the provider will keep failing for a while (rejected key, exhausted quota), so the chain
    tries the others first until then.
    """

    def __init__(self, message: str, cooldown_s: float = 0.0) -> None:
        super().__init__(message)
        self.cooldown_s = cooldown_s


def _cooldown_for(response: httpx.Response) -> float:
    status = response.status_code
    if status in PERMANENT_STATUS:
        return REJECTED_COOLDOWN_SECONDS
    if status == 429 and _is_billing_error(response):
        wait = _provider_retry_delay(response)
        return min(wait, REJECTED_COOLDOWN_SECONDS) if wait else QUOTA_COOLDOWN_SECONDS
    return 0.0


def _why(response: httpx.Response) -> str:
    """The provider's own short reason for a 400 or 404 (a bad request, an unknown model), so a log line says what to
    fix. Never given for other statuses: a rejected key's message can echo part of the key."""
    if response.status_code not in (400, 404):
        return ""
    try:
        error = response.json()["error"]
        reason = (error.get("message") or error.get("code")) if isinstance(error, dict) else error
    except (ValueError, KeyError, TypeError):
        return ""
    return f": {' '.join(str(reason).split())[:80]}" if reason else ""


def _time_left(timeout_s: float) -> float:
    """The timeout for the next request: the configured one, cut short by the chain's remaining budget."""
    deadline = _deadline.get()
    if deadline is None:
        return timeout_s
    left = deadline - time.monotonic()
    if left < MIN_USEFUL_SECONDS:
        raise LLMError("time budget used up")
    return min(timeout_s, left)


@contextmanager
def deadline_within(seconds: float) -> Iterator[None]:
    """Every model call inside the block, retries and fallback providers included, ends within `seconds`."""
    moment = time.monotonic() + seconds
    current = _deadline.get()
    token = _deadline.set(moment if current is None else min(current, moment))
    try:
        yield
    finally:
        _deadline.reset(token)


def _pause(seconds: float) -> None:
    """Sleep, but never past the budget; a retry that cannot finish is not attempted."""
    deadline = _deadline.get()
    if deadline is not None and deadline - time.monotonic() < seconds + MIN_USEFUL_SECONDS:
        raise LLMError("time budget used up")
    time.sleep(seconds)


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
            raise LLMError(f"no API key for {config.provider}")
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
                    timeout=_time_left(self.config.timeout_s),
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
                wait = _provider_retry_delay(exc.response)
                daily = wait is not None and wait > MAX_PROVIDER_WAIT_SECONDS
                cooldown = REJECTED_COOLDOWN_SECONDS if daily else _cooldown_for(exc.response)
                last_error = LLMError(
                    f"HTTP {exc.response.status_code} from {self.config.provider}{_why(exc.response)}", cooldown
                )
                if exc.response.status_code not in TRANSIENT_STATUS or cooldown:
                    break  # rejected, or out of quota: the next provider is the better use of the time
                if wait is not None and attempt < self.config.max_retries:
                    _pause(wait)
                    continue
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_error = LLMError(
                    f"{type(exc).__name__}: cannot reach {self.config.provider}", UNREACHABLE_COOLDOWN_SECONDS
                )
                break
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                # Never include the request: its headers carry the key.
                last_error = LLMError(f"{type(exc).__name__}: {str(exc)[:120]}".replace(self._api_key, "<key>"))
            if attempt < self.config.max_retries:
                _pause(BACKOFF_SECONDS * (attempt + 1))
        raise last_error or LLMError("LLM call failed")


OPENAI_COMPATIBLE = {
    "groq": ("https://api.groq.com/openai/v1", "groqcloud_api_key", "llm_model_groq"),
    "openai": ("https://api.openai.com/v1", "openai_api_key", "llm_model_openai"),
    "mistral": ("https://api.mistral.ai/v1", "mistral_api_key", "llm_model_mistral"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter_api_key", "llm_model_openrouter"),
}


class OpenAICompatibleAdapter:
    """Chat-completions API shared by Groq, OpenRouter, Mistral and OpenAI."""

    def __init__(self, config: LLMConfig, api_key: str, base_url: str, key_required: bool = True) -> None:
        if key_required and not api_key:
            raise LLMError(f"no API key for {config.provider}")
        self.config = config
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/chat/completions"

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
                    self._url, json=body, headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else {},
                    timeout=_time_left(self.config.timeout_s),
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
                cooldown = _cooldown_for(exc.response)
                last_error = LLMError(
                    f"HTTP {exc.response.status_code} from {self.config.provider}{_why(exc.response)}", cooldown
                )
                if exc.response.status_code not in TRANSIENT_STATUS or cooldown:
                    break
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_error = LLMError(
                    f"{type(exc).__name__}: cannot reach {self.config.provider}", UNREACHABLE_COOLDOWN_SECONDS
                )
                break
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                message = f"{type(exc).__name__}: {str(exc)[:120]}"
                last_error = LLMError(message.replace(self._api_key, "<key>") if self._api_key else message)
            if attempt < self.config.max_retries:
                _pause(BACKOFF_SECONDS * (attempt + 1))
        raise last_error or LLMError("LLM call failed")


def _call_slots(size: int) -> threading.BoundedSemaphore:
    global _slots
    with _slots_lock:
        if _slots is None or _slots[0] != size:
            _slots = (size, threading.BoundedSemaphore(size))
        return _slots[1]


class FallbackChain:
    """Tries each provider in order; the next one is used when one fails or has no quota left.

    A provider that recently rejected the key or ran out of quota is tried last until its cooldown ends, so a dead
    key does not cost time on every request, yet is still used if everything else fails.
    """

    def __init__(
        self, adapters: list[LLMAdapter], budget_s: float = 20.0, max_concurrent: int = 16, queue_wait_s: float = 3.0
    ) -> None:
        self.adapters = adapters
        self.budget_s = budget_s
        self.max_concurrent = max_concurrent
        self.queue_wait_s = queue_wait_s
        self.last: LLMAdapter = adapters[0]

    @property
    def config(self) -> LLMConfig:
        """The provider that answered last (or the first, before any call)."""
        return self.last.config

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> str:
        """At most `max_concurrent` calls run at once in this process; one that cannot start within `queue_wait_s`
        fails as if the model were down, so a crowd of waiting requests cannot use every thread and connection."""
        slots = _call_slots(self.max_concurrent)
        if not slots.acquire(timeout=self.queue_wait_s):
            raise LLMError("too many model calls are waiting; try again shortly")
        try:
            return self._complete(system, user, json_schema)
        finally:
            slots.release()

    def _complete(self, system: str, user: str, json_schema: dict | None = None) -> str:
        """One answer within `budget_s` seconds in total, however many providers have to be tried, and never past a
        deadline the caller has already set."""
        mine = time.monotonic() + self.budget_s
        outer = _deadline.get()
        token = _deadline.set(mine if outer is None else min(outer, mine))
        errors = []
        now = time.monotonic()
        cooling = [a for a in self.adapters if _cooling.get(_key(a), 0.0) > now]
        ordered = [a for a in self.adapters if a not in cooling] + cooling
        try:
            for position, adapter in enumerate(ordered):
                left = _deadline.get() - time.monotonic()
                share = left / min(len(ordered) - position, MAX_SHARE_DIVISOR)
                last = position == len(ordered) - 1
                share_ends = time.monotonic() + share
                try:
                    with deadline_within(left if last or share < MIN_USEFUL_SECONDS else share):
                        reply = adapter.complete(system, user, json_schema)
                except LLMError as exc:
                    cooldown_s = exc.cooldown_s
                    if not cooldown_s and not last and time.monotonic() >= share_ends - 0.5:
                        cooldown_s = SLOW_COOLDOWN_SECONDS
                    if cooldown_s:
                        _cooling[_key(adapter)] = time.monotonic() + cooldown_s
                    errors.append(f"{adapter.config.provider}/{adapter.config.model}: {exc}")
                    log.warning(
                        "provider failed, trying the next",
                        extra={"fields": {"provider": adapter.config.provider, "model": adapter.config.model,
                                          "cooldown_s": cooldown_s}},
                    )
                    continue
                _cooling.pop(_key(adapter), None)
                self.last = adapter
                return reply
        finally:
            _deadline.reset(token)
        raise LLMError("every provider failed: " + "; ".join(errors))


def _key(adapter: LLMAdapter) -> tuple[str, str]:
    return adapter.config.provider, adapter.config.model


# A model served on this machine or inside the institution (Ollama, vLLM, LM Studio, ...): any OpenAI-compatible
# server at LOCAL_LLM_BASE_URL, with no key needed. Student code then never leaves the institution (TR-S-09).
LOCAL = "local"

# Gemini keys: provider -> (settings field holding the key, settings field holding its default model)
GEMINI_KEYS = {
    "gemini": ("gemini_api_key", "llm_model_gemini"),
    "gemini_pro": ("gemini_pro_api_key", "llm_model_gemini_pro"),
}


def build_adapter(settings: Settings) -> LLMAdapter:
    """The primary from LLM_PROVIDER/LLM_MODEL, then LLM_FALLBACK in order. A fallback is `provider` or
    `provider:model`, so one key can serve several models, e.g. `gemini_pro:gemini-3.1-pro-preview,groq`."""

    def config(provider: str, model: str) -> LLMConfig:
        return LLMConfig(
            provider=provider, model=model, timeout_s=settings.llm_timeout_s, max_retries=settings.llm_max_retries,
            temperature=settings.llm_temperature, thinking_budget=settings.llm_thinking_budget,
        )

    def make(provider: str, model: str | None) -> LLMAdapter:
        if provider in GEMINI_KEYS:
            key_field, model_field = GEMINI_KEYS[provider]
            model = model or getattr(settings, model_field)
            return GeminiAdapter(config(provider, model), getattr(settings, key_field))
        if provider == LOCAL:
            if not settings.local_llm_base_url:
                raise LLMError("LOCAL_LLM_BASE_URL is not set")
            return OpenAICompatibleAdapter(
                config(LOCAL, model or settings.llm_model_local), settings.local_llm_api_key,
                settings.local_llm_base_url, key_required=False,
            )
        if provider in OPENAI_COMPATIBLE:
            base_url, key_field, model_field = OPENAI_COMPATIBLE[provider]
            return OpenAICompatibleAdapter(
                config(provider, model or getattr(settings, model_field)), getattr(settings, key_field), base_url
            )
        raise ValueError(f"unsupported LLM provider: {provider}")

    if settings.llm_provider == "stub":
        return StubAdapter(config("stub", settings.llm_model))
    adapters = [make(settings.llm_provider, settings.llm_model)]
    for entry in (e.strip() for e in settings.llm_fallback.split(",") if e.strip()):
        provider, _, model = entry.partition(":")
        if provider not in GEMINI_KEYS and provider not in OPENAI_COMPATIBLE and provider != LOCAL:
            raise ValueError(f"unsupported fallback provider: {provider}")
        try:
            adapters.append(make(provider, model.strip() or None))
        except LLMError:
            log.warning("fallback provider skipped: no key", extra={"fields": {"provider": provider}})
    return FallbackChain(adapters, settings.llm_budget_s, settings.llm_max_concurrent, settings.llm_queue_wait_s)
