from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret: str
    mastery_service_url: str
    mastery_service_token: str
    jwt_expire_minutes: int = 60

    llm_provider: str = "stub"
    llm_model: str = "stub"
    llm_timeout_s: float = 12  # one request to one provider
    llm_budget_s: float = 20  # the whole answer, across retries and fallback providers
    llm_max_retries: int = 1
    llm_temperature: float = 0.1
    llm_thinking_budget: int = 0
    gemini_api_key: str = ""
    llm_fallback: str = ""  # providers tried in order when the primary fails, e.g. "groq,deepseek,openai"
    groqcloud_api_key: str = ""
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    mistral_api_key: str = ""
    openrouter_api_key: str = ""
    llm_model_groq: str = "openai/gpt-oss-20b"
    llm_model_deepseek: str = "deepseek-flash"
    llm_model_openai: str = "gpt-4.1-mini"
    llm_model_mistral: str = "mistral-small-2603"
    llm_model_openrouter: str = "nvidia/nemotron-3-super-120b-a12b:free"
    chat_database_url: str = ""
    router_min_confidence: float = 0.6
    chat_history_turns: int = 6
    retrieval_min_score: float = 0.67


@lru_cache
def get_settings() -> Settings:
    return Settings()
