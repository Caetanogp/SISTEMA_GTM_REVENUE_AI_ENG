"""Settings for the FastAPI composition root."""

from __future__ import annotations

from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    environment: str = Field(default="local", alias="ENVIRONMENT")
    demo_mode: bool = Field(default=True, alias="DEMO_MODE")
    database_url: str = Field(
        default="postgresql+psycopg://revops:revops@localhost:5432/revops",
        alias="DATABASE_URL",
    )
    jwt_secret: str = Field(default="change-me-locally", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_ttl_minutes: int = Field(default=60, alias="ACCESS_TOKEN_TTL_MINUTES")
    broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    result_backend: str = Field(default="redis://localhost:6379/1", alias="CELERY_RESULT_BACKEND")

    @cached_property
    def postgres_dsn(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
