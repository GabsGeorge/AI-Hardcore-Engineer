from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration comes from the environment (constitution II)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"

    openai_api_key: SecretStr | None = None
    openai_model_primary: str = ""
    openai_model_fallback: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    jwt_secret: SecretStr
    jwt_issuer: str = "getnet-support"
    jwt_audience: str = "getnet-support-api"

    database_url: str
    redis_url: str

    max_steps: int = Field(6, ge=1)
    token_budget_per_run: int = Field(20_000, ge=1)
    confidence_replan: float = Field(0.70, ge=0, le=1)
    confidence_escalate_hard: float = Field(0.40, ge=0, le=1)
    rag_relevance_threshold: float = Field(0.30, ge=0, le=1)

    rate_limit_per_min: int = Field(30, ge=1)
    handoff_sla_minutes: int = Field(15, ge=1)
    handoff_expiry_hours: int = Field(24, ge=1)

    retention_conversation_days: int = Field(90, ge=1)
    retention_log_days: int = Field(30, ge=1)
    retention_audit_days: int = Field(365, ge=1)

    eval_sample_rate: float = Field(0.10, ge=0, le=1)
    otel_exporter_otlp_endpoint: str = ""
    metrics_port: int = Field(9100, ge=0)  # internal only; 0 disables the exporter

    seed_reference_date: date | None = None

    @field_validator("jwt_secret")
    @classmethod
    def _strong_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET must have at least 32 bytes")
        return value

    @field_validator("seed_reference_date", mode="before")
    @classmethod
    def _empty_date_is_none(cls, value: object) -> object:
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
