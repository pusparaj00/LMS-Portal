from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str
    redis_url: str

    llm_provider: str = "stub"
    llm_model: str = "stub"
    llm_timeout_s: float = 30
    llm_max_retries: int = 1
    llm_temperature: float = 0.1


@lru_cache
def get_settings() -> Settings:
    return Settings()
