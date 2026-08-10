from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    question_time_limit: float = 20.0
    max_players_per_room: int = 20
    room_code_length: int = 6
    allowed_origins: str = "http://localhost:3000"
    openrouter_api_key: str = ""
    openrouter_model: str = "inclusionai/ling-3.0-flash:free"
    openrouter_fallback_model: str = "google/gemma-4-26b-a4b-it:free"
    ai_timeout: float = 20.0
    database_url: str = "sqlite:///./quiz.db"
    log_level: str = "INFO"
    rate_limit_create: int = 30
    rate_limit_join: int = 60
    trust_proxy_headers: bool = False

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def model_chain(self) -> list[str]:
        return [
            m
            for m in (self.openrouter_model, self.openrouter_fallback_model)
            if m
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()