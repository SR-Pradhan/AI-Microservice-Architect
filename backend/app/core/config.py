"""Application settings, loaded once from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+asyncpg://architect:architect@localhost:5434/architect"
    cors_origins: str = "http://localhost:5173"

    # Claude. The key is read from the environment and must never be committed.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    anthropic_max_tokens: int = 16000
    # How many times a stage may be re-asked after the output fails validation.
    llm_max_retries: int = 2

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached so every import shares one Settings instance."""
    return Settings()
