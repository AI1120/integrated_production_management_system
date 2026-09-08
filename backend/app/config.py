"""Application configuration.

Everything is overridable through environment variables (prefix ``IPMS_``) or a
``.env`` file, so the same image can run for the sample factory today and the
multi-plant deployment later.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IPMS_", env_file=".env", extra="ignore")

    app_name: str = "IPMS - Integrated Production Management System"
    version: str = "0.1.0"

    # SQLite for the sample factory; swap for postgresql+psycopg://... in production.
    database_url: str = f"sqlite:///{BASE_DIR / 'ipms.db'}"
    sql_echo: bool = False

    secret_key: str = "change-me-in-production-please-use-a-real-secret"
    access_token_expire_minutes: int = 60 * 12

    # Plant identity - the big-factory rollout runs one deployment per site.
    plant_code: str = "PLANT-01"
    plant_name: str = "Sample Assembly Factory"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
