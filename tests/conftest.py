"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep tests independent from the developer's local .env file."""
    monkeypatch.delenv("TRACEHUB_ENV", raising=False)
    yield
