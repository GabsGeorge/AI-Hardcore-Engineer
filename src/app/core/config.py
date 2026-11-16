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

    # Feature 002 web UI. Session cookies use session_secret; password hashing uses the pepper.
    # SMTP points at Mailpit in dev; set a real provider URL in production.
    session_secret: SecretStr | None = None
    password_pepper: SecretStr | None = None
    smtp_url: str = ""
    web_base_url: str = "http://localhost"
    admin_seed_email: str = "admin@getnet.example.com"
    admin_seed_password: SecretStr | None = None

    database_url: str
    redis_url: str

    max_steps: int = Field(6, ge=1)
    token_budget_per_run: int = Field(20_000, ge=1)
    # Thresholds originais do contrato. Valores anteriores (0.50/0.25) foram atalhos
    # para mascarar hedge do modelo; voltamos a 0.70/0.40 e a calibração do retriever
    # cabe ao score real (não ao supervisor).
    confidence_replan: float = Field(0.70, ge=0, le=1)
    confidence_escalate_hard: float = Field(0.40, ge=0, le=1)
    # Estratégia de retrieval escolhida pelos dados de `evals/retrieval_compare.py` (ADR 0003):
    # densa venceu híbrida e híbrida+rerank em recall@5, MRR e nDCG@5 neste corpus.
    rag_strategy: Literal["dense", "hybrid_rerank"] = "dense"
    # Limiar da estratégia densa (similaridade de cosseno), calibrado em
    # `evals/dense_threshold_sweep.py` (14 perguntas rotuladas, 10 sem fonte): o recall@5 não
    # muda até 0,525, mas a comparação curta do enunciado ("Get Clássica e Get Smart") fica em
    # 0,437 e "Get Turbo X" (inexistente) em 0,47-0,49, então nenhum corte separa os dois.
    # 0,40 dá folga sobre o pior caso legítimo; a recusa do que não existe fica com a resposta
    # (confiança) e o grounding sobre o texto das fontes.
    rag_dense_threshold: float = Field(0.40, ge=0, le=1)
    # Cosseno a partir do qual um trecho conta como acerto forte (score 1.0). Entre o limiar e
    # este valor o score sobe linearmente de `confidence_replan` até 1.0 (ver dense_relevance).
    rag_dense_strong: float = Field(0.70, ge=0, le=1)
    # Limiar do score do reranker na estratégia `hybrid_rerank` (escala diferente da densa).
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
