from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://contest:contest@localhost:5432/contest"
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    judge_image: str = "contest-python:3.12"
    judge_timeout_seconds: float = 3.0
    judge_max_output_bytes: int = 65536
    judge_max_attempts: int = 3
    judge_lease_seconds: int = 60
    judge_temp_dir: str = "/tmp/contest-judge"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
