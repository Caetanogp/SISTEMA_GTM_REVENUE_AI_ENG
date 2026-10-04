"""Environment-backed settings for the Celery worker composition root."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field(
        default="postgresql+psycopg://revops:revops@localhost:5432/revops",
        alias="DATABASE_URL",
    )
    broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    result_backend: str = Field(default="redis://localhost:6379/2", alias="CELERY_RESULT_BACKEND")
    knowledge_embedding_provider: str = Field(default="fake", alias="KNOWLEDGE_EMBEDDING_PROVIDER")
    knowledge_embedding_model: str = Field(
        default="text-embedding-3-small", alias="KNOWLEDGE_EMBEDDING_MODEL"
    )
    knowledge_embedding_dimension: int = Field(default=1536, alias="KNOWLEDGE_EMBEDDING_DIMENSION")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
