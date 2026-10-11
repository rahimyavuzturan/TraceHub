"""Application settings.

All configuration is read from environment variables (or a local ``.env`` file)
with the ``TRACEHUB_`` prefix. Nested settings use ``__`` as delimiter, e.g.
``TRACEHUB_LLM__MODEL``.

Never read ``os.environ`` directly elsewhere in the codebase; import ``settings``
from this module instead.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class LLMProvider(StrEnum):
    MOCK = "mock"
    OPENAI_COMPATIBLE = "openai_compatible"


class EmbeddingProvider(StrEnum):
    HASH = "hash"
    OPENAI_COMPATIBLE = "openai_compatible"


class LLMSettings(BaseModel):
    provider: LLMProvider = LLMProvider.MOCK
    base_url: str = "http://localhost:8000/v1"
    model: str = "Qwen/Qwen3-32B-Instruct"
    api_key: SecretStr = SecretStr("")
    timeout_seconds: float = 120.0
    max_tokens: int = 4096
    temperature: float = 0.1


class EmbeddingSettings(BaseModel):
    provider: EmbeddingProvider = EmbeddingProvider.HASH
    base_url: str = "http://localhost:8080/v1"
    model: str = "BAAI/bge-m3"
    api_key: SecretStr = SecretStr("")
    timeout_seconds: float = 60.0
    dimensions: int = 1024
    batch_size: int = 16


class KnowledgeBaseSettings(BaseModel):
    root: Path = Path("knowledge")
    chunk_tokens: int = 700
    chunk_overlap_tokens: int = 100

    def resolved_root(self) -> Path:
        return self.root if self.root.is_absolute() else REPO_ROOT / self.root


class BudgetSettings(BaseModel):
    """Hard limits that keep an autonomous investigation bounded."""

    max_steps: int = 25
    max_seconds: int = 600
    max_tool_output_chars: int = 20_000


class ApiSettings(BaseModel):
    host: str = "0.0.0.0"  # noqa: S104 - container icinde tum arayuzlerden dinlenir
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    jwt_secret: SecretStr = SecretStr("change-me")
    jwt_ttl_minutes: int = 720


class KubernetesSettings(BaseModel):
    """How the read-only Kubernetes tools reach a cluster.

    The logical environment maps to a kubeconfig context via
    ``config/environments.yaml``; this only says where the kubeconfig lives.
    """

    kubeconfig: Path = Path.home() / ".kube" / "config"
    timeout_seconds: float = 30.0

    def resolved_kubeconfig(self) -> Path:
        return self.kubeconfig if self.kubeconfig.is_absolute() else REPO_ROOT / self.kubeconfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRACEHUB_",
        env_nested_delimiter="__",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    log_level: str = "INFO"
    log_json: bool = False
    database_url: str = "postgresql+asyncpg://tracehub:tracehub_dev_only@localhost:5433/tracehub"

    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    kb: KnowledgeBaseSettings = Field(default_factory=KnowledgeBaseSettings)
    budget: BudgetSettings = Field(default_factory=BudgetSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    kubernetes: KubernetesSettings = Field(default_factory=KubernetesSettings)

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"prod", "production"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
