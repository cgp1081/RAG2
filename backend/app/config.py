"""Application configuration powered by pydantic-settings.

The settings expose connectivity for the primary Postgres database used by the
SQLAlchemy session factory. Future components should rely on
``Settings.database_url`` rather than hard-coding URIs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Generator

from dotenv import dotenv_values
from pydantic import AnyHttpUrl, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration loaded from environment variables."""

    app_env: str = "development"
    log_level: str = "INFO"
    postgres_url: AnyHttpUrl | str = "postgresql+psycopg://postgres:postgres@postgres:5432/postgres"
    qdrant_url: AnyHttpUrl | str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    app_version: str = "0.1.0"
    database_url: PostgresDsn | str = (
        "postgresql+psycopg://postgres:postgres@postgres:5432/postgres"
    )
    db_pool_size: int = 10
    admin_api_key: str | None = None
    embedding_model: str = "nomic-embed-text"
    ollama_base_url: AnyHttpUrl | str = "http://ollama:11434"
    llm_base_url: AnyHttpUrl | str = "http://ollama:11434"
    llm_model: str = "mistral"
    llm_max_tokens: int = 512
    llm_timeout_seconds: float = 15.0
    chat_api_key: str | None = None
    chat_timeout_seconds: float = 20.0
    chat_max_tokens: int = 600
    structured_max_rows: int = 50000
    structured_sample_size: int = 5
    sql_query_timeout_seconds: float = 5.0
    sql_allowed_functions: list[str] = ["count", "sum", "avg", "min", "max"]
    vector_dim: int = 1536
    vector_timeout_seconds: float = 10.0
    embedding_fallback_models: list[str] = []
    local_ingest_root: Path | str = Path("./data")
    chunk_size: int = 400
    chunk_overlap: int = 40
    ingest_default_tenant: str = "default"
    retrieval_top_k_default: int = 8
    retrieval_score_floor: float = 0.35
    retrieval_score_ceiling: float = 0.95
    retrieval_diagnostics: bool = False
    observability_enabled: bool = True
    prometheus_enabled: bool = True
    prometheus_port: int = 9100
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: AnyHttpUrl | None = None
    trace_sample_rate: float = 0.1
    eval_top_k: int = 5
    eval_output_dir: Path | str = Path("reports")

    model_config = SettingsConfigDict(env_prefix="", extra="ignore", case_sensitive=False)

    @classmethod
    def load(cls) -> "Settings":
        """Create settings by merging `.env` values with the environment."""

        env_path = Path(".env")
        file_values = dotenv_values(str(env_path)) if env_path.exists() else {}
        merged = {**file_values, **os.environ}
        if "DATABASE_URL" not in merged and "POSTGRES_URL" in merged:
            merged["DATABASE_URL"] = merged["POSTGRES_URL"]
        if "DB_POOL_SIZE" not in merged and "DATABASE_POOL_SIZE" in merged:
            merged["DB_POOL_SIZE"] = merged["DATABASE_POOL_SIZE"]
        # BaseSettings will re-read the OS environment, so pass merged as data.
        return cls(**merged)

    @field_validator("embedding_fallback_models", mode="before")
    @classmethod
    def _parse_fallback_models(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("Invalid fallback model list")

    @field_validator("sql_allowed_functions", mode="before")
    @classmethod
    def _parse_allowed_functions(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        raise ValueError("Invalid SQL allowed function list")

    @dataclass(slots=True)
    class IngestionConfig:
        local_root: Path
        chunk_size: int
        chunk_overlap: int
        default_tenant: str
        vector_dim: int

    def ingestion_config(self) -> "Settings.IngestionConfig":
        return self.IngestionConfig(
            local_root=Path(self.local_ingest_root).resolve(),
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            default_tenant=self.ingest_default_tenant,
            vector_dim=self.vector_dim,
        )

    @dataclass(slots=True)
    class StructuredConfig:
        default_tenant: str
        max_rows: int
        sample_size: int

    def structured_config(self) -> "Settings.StructuredConfig":
        return self.StructuredConfig(
            default_tenant=self.ingest_default_tenant,
            max_rows=self.structured_max_rows,
            sample_size=self.structured_sample_size,
        )

    @dataclass(slots=True)
    class SQLGuardConfig:
        timeout_seconds: float
        allowed_functions: list[str]

    def sql_guard_config(self) -> "Settings.SQLGuardConfig":
        return self.SQLGuardConfig(
            timeout_seconds=self.sql_query_timeout_seconds,
            allowed_functions=list({func.lower() for func in self.sql_allowed_functions}),
        )

    @dataclass(slots=True)
    class ObservabilityConfig:
        observability_enabled: bool
        prometheus_enabled: bool
        prometheus_port: int
        otel_enabled: bool
        otel_exporter_otlp_endpoint: AnyHttpUrl | None
        trace_sample_rate: float

    def observability_config(self) -> "Settings.ObservabilityConfig":
        return self.ObservabilityConfig(
            observability_enabled=self.observability_enabled,
            prometheus_enabled=self.prometheus_enabled,
            prometheus_port=self.prometheus_port,
            otel_enabled=self.otel_enabled,
            otel_exporter_otlp_endpoint=self.otel_exporter_otlp_endpoint,
            trace_sample_rate=self.trace_sample_rate,
        )

    @dataclass(slots=True)
    class EvalConfig:
        top_k: int
        output_dir: Path

    def eval_config(self) -> "Settings.EvalConfig":
        return self.EvalConfig(
            top_k=max(int(self.eval_top_k), 1),
            output_dir=Path(self.eval_output_dir).resolve(),
        )


def _build_settings() -> Settings:
    return Settings.load()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return _build_settings()


def settings_dependency() -> Generator[Settings, None, None]:
    """FastAPI dependency that yields the cached settings."""

    yield get_settings()


def get_admin_api_key() -> str | None:
    """Return the configured admin API key, if any."""

    return get_settings().admin_api_key


__all__ = [
    "Settings",
    "get_settings",
    "settings_dependency",
    "get_admin_api_key",
]
