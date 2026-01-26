"""Configuration settings using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    discord_token: str
    database_url: str = "sqlite+aiosqlite:///data/ephemeral_vc.db"


settings = Settings()
