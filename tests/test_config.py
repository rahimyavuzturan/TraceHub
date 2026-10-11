"""T0.2 - configuration must be overridable from the environment and stay typed."""

from __future__ import annotations

import pytest

from tracehub_core.config import EmbeddingProvider, LLMProvider, Settings, get_settings


def test_defaults_are_safe() -> None:
    config = Settings(_env_file=None)  # type: ignore[call-arg]
    assert config.env == "dev"
    assert config.is_production is False
    assert config.llm.provider is LLMProvider.MOCK
    assert config.embedding.provider is EmbeddingProvider.HASH
    assert config.budget.max_steps > 0


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACEHUB_ENV", "prod")
    monkeypatch.setenv("TRACEHUB_LOG_LEVEL", "DEBUG")

    config = Settings(_env_file=None)  # type: ignore[call-arg]

    assert config.env == "prod"
    assert config.log_level == "DEBUG"
    assert config.is_production is True


def test_nested_settings_use_double_underscore(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACEHUB_LLM__PROVIDER", "openai_compatible")
    monkeypatch.setenv("TRACEHUB_LLM__MODEL", "test-model")
    monkeypatch.setenv("TRACEHUB_BUDGET__MAX_STEPS", "7")

    config = Settings(_env_file=None)  # type: ignore[call-arg]

    assert config.llm.provider is LLMProvider.OPENAI_COMPATIBLE
    assert config.llm.model == "test-model"
    assert config.budget.max_steps == 7


def test_secrets_are_not_exposed_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACEHUB_LLM__API_KEY", "super-secret-token")

    config = Settings(_env_file=None)  # type: ignore[call-arg]

    assert "super-secret-token" not in repr(config)
    assert config.llm.api_key.get_secret_value() == "super-secret-token"


def test_knowledge_base_root_resolves_to_absolute_path() -> None:
    config = Settings(_env_file=None)  # type: ignore[call-arg]
    assert config.kb.resolved_root().is_absolute()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
