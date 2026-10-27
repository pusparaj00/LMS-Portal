from functools import lru_cache
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDERS = ("changeme", "change-me", "change_me", "secret", "password", "example", "placeholder")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: str = "development"  # "production" makes the secret checks below fatal (TR-O-04)
    database_url: str
    redis_url: str
    jwt_secret: str
    mastery_service_url: str
    mastery_service_token: str
    jwt_expire_minutes: int = 60
    # One request holds one connection for its whole run (a chat request holds one from each of two pools), so each pool
    # must cover the server's worker threads. Postgres is started with max_connections=200: 70 + 70 here and about 15
    # for the mastery service and the worker. Measured in docs/results/step-70-small-fixes.md.
    server_threads: int = 70  # requests running at once
    db_pool_size: int = 45
    db_max_overflow: int = 25
    db_pool_timeout_s: float = 10
    retention_days: int = 0  # erase a student's data after this many days without activity; 0 keeps it
    audit_retention_days: int = 0  # remove audit events older than this; 0 keeps them
    tool_base_url: str = ""  # this app's public address as the LMS sees it (LTI, TR-A-09); empty turns LTI off
    lti_keys_timeout_s: float = 5  # each call to an LMS: its public keys (cached for an hour), tokens, grades
    lti_tool_private_key: str = ""  # base64 PEM from `app.manage lti-tool-key`; signs grade requests. Secret.

    llm_provider: str = "stub"
    llm_model: str = "stub"
    llm_timeout_s: float = 12  # one request to one provider
    llm_budget_s: float = 20  # the whole answer, across retries and fallback providers
    # Model calls in flight at once. A request holds a worker thread and a database connection while it waits for the
    # model, so without a cap a class asking together uses them all and cheap requests wait behind it. A call that
    # cannot start within llm_queue_wait_s fails like a model outage, which every caller already handles.
    llm_max_concurrent: int = 16
    llm_queue_wait_s: float = 3
    # A new explanation, both attempts and their checks, ends within this; then the template is shown (TR-P-03, 15 s).
    explain_budget_s: float = 14
    llm_max_retries: int = 1
    llm_temperature: float = 0.1
    llm_thinking_budget: int = 0
    gemini_api_key: str = ""
    gemini_pro_api_key: str = ""
    # tried in order when the primary fails: `provider` or `provider:model`, e.g. "gemini_pro,groq,openai"
    llm_fallback: str = ""
    groqcloud_api_key: str = ""
    openai_api_key: str = ""
    mistral_api_key: str = ""
    openrouter_api_key: str = ""
    llm_model_gemini: str = "gemini-3.5-flash-lite"
    llm_model_gemini_pro: str = "gemini-3.5-flash-lite"
    local_llm_base_url: str = ""  # e.g. http://host.docker.internal:11434/v1 for Ollama
    local_llm_api_key: str = ""
    llm_model_local: str = ""
    llm_model_groq: str = "openai/gpt-oss-20b"
    llm_model_openai: str = "gpt-4.1-mini"
    llm_model_mistral: str = "mistral-small-2603"
    llm_model_openrouter: str = "nvidia/nemotron-3-super-120b-a12b:free"
    chat_database_url: str = ""
    router_min_confidence: float = 0.6
    # The routing call, retries and fallback providers included. Past it the keyword rules route, so a student whose
    # providers are all rate-limited is not left waiting for the slowest model in the chain.
    router_budget_s: float = 3
    chat_history_turns: int = 6
    retrieval_min_score: float = 0.67

    def check_production(self) -> None:
        """A pydantic validator would echo the offending values in its error; this names only the setting."""
        if self.app_env != "production":
            return
        weak = []
        for name, value, shortest in (
            ("JWT_SECRET", self.jwt_secret, 32),
            ("MASTERY_SERVICE_TOKEN", self.mastery_service_token, 32),
            ("database password", urlsplit(self.database_url).password or "", 16),
            ("Redis password", urlsplit(self.redis_url).password or "", 16),
        ):
            if len(value) < shortest or any(word in value.lower() for word in PLACEHOLDERS):
                weak.append(f"{name} (at least {shortest} characters, not a placeholder)")
        if weak:
            raise RuntimeError("APP_ENV=production refuses weak secrets: " + "; ".join(weak))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.check_production()
    return settings
