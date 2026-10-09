"""Settings for the FastAPI composition root."""

from __future__ import annotations

from functools import cached_property
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
    llm_gateway_mode: Literal["disabled", "live"] = Field(
        default="disabled", alias="LLM_GATEWAY_MODE"
    )
    llm_primary_provider: str = Field(default="openai", alias="LLM_PRIMARY_PROVIDER")
    llm_fallback_provider: str = Field(default="anthropic", alias="LLM_FALLBACK_PROVIDER")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_model: str = Field(default="gpt-5.6-terra", alias="OPENAI_MODEL")
    anthropic_model: str = Field(default="claude-sonnet-5", alias="ANTHROPIC_MODEL")
    llm_max_output_tokens: int = Field(default=2048, ge=1, alias="LLM_MAX_OUTPUT_TOKENS")
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0, alias="LLM_TEMPERATURE")
    llm_request_timeout_seconds: float = Field(
        default=30.0, gt=0.0, alias="LLM_REQUEST_TIMEOUT_SECONDS"
    )
    llm_call_deadline_seconds: float = Field(
        default=90.0, gt=0.0, alias="LLM_CALL_DEADLINE_SECONDS"
    )
    llm_max_retries: int = Field(default=2, ge=0, le=5, alias="LLM_MAX_RETRIES")
    llm_backoff_base_seconds: float = Field(default=0.5, gt=0.0, alias="LLM_BACKOFF_BASE_SECONDS")
    llm_backoff_max_seconds: float = Field(default=8.0, gt=0.0, alias="LLM_BACKOFF_MAX_SECONDS")
    knowledge_embedding_provider: Literal["fake", "openai"] = Field(
        default="fake", alias="KNOWLEDGE_EMBEDDING_PROVIDER"
    )
    knowledge_embedding_model: str = Field(
        default="text-embedding-3-small", alias="KNOWLEDGE_EMBEDDING_MODEL"
    )
    knowledge_embedding_dimension: int = Field(
        default=1536, gt=0, alias="KNOWLEDGE_EMBEDDING_DIMENSION"
    )
    research_enabled: bool = Field(default=False, alias="RESEARCH_ENABLED")
    research_sources_json: str = Field(default="{}", alias="RESEARCH_SOURCES_JSON")
    research_deadline_seconds: float = Field(
        default=30.0, gt=0.0, alias="RESEARCH_DEADLINE_SECONDS"
    )

    @field_validator("llm_primary_provider", "llm_fallback_provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: object) -> str:
        return str(value).strip().lower()

    @cached_property
    def postgres_dsn(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
