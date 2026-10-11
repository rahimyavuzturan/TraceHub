"""T0.1 - verify that the workspace packages are importable and wired together."""

from __future__ import annotations

import importlib

import pytest

WORKSPACE_PACKAGES = ["tracehub_core", "tracehub_kb", "tracehub_api"]


@pytest.mark.parametrize("package", WORKSPACE_PACKAGES)
def test_workspace_package_is_importable(package: str) -> None:
    assert importlib.import_module(package) is not None


def test_core_exposes_version() -> None:
    import tracehub_core

    assert tracehub_core.__version__


def test_cli_app_is_registered() -> None:
    from tracehub_core.cli import app

    command_names = {command.callback.__name__ for command in app.registered_commands}
    assert {"version", "info"} <= command_names
