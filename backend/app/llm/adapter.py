from dataclasses import dataclass
from typing import Protocol

from app.config import Settings


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    timeout_s: float
    max_retries: int
    temperature: float


class LLMAdapter(Protocol):
    config: LLMConfig

    def complete(self, system: str, user: str) -> str: ...


class StubAdapter:
    """Canned reply used before Step 4; the only allowed stub."""

    reply = "This is a canned reply from the stub LLM adapter."

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, system: str, user: str) -> str:
        return self.reply


def build_adapter(settings: Settings) -> LLMAdapter:
    config = LLMConfig(
        provider=settings.llm_provider,
        model=settings.llm_model,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        temperature=settings.llm_temperature,
    )
    if config.provider == "stub":
        return StubAdapter(config)
    raise ValueError(f"unsupported LLM_PROVIDER: {config.provider}")
