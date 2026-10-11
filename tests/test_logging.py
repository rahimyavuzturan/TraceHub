"""T0.2 - logging must never write to stdout.

STDIO based MCP servers speak JSON-RPC over stdout; a single stray byte there
corrupts the protocol. This test is the regression guard for that rule.
"""

from __future__ import annotations

import pytest

from tracehub_core.logging import configure_logging, get_logger


def test_log_output_goes_to_stderr_not_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(force=True)
    logger = get_logger("tracehub.test")

    logger.warning("stdout_must_stay_clean", detail="mcp-protocol")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "stdout_must_stay_clean" in captured.err


def test_bound_context_is_rendered(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(force=True)
    logger = get_logger("tracehub.test").bind(session_id="abc-123")

    logger.warning("tool_call_started", tool="pod_logs")

    captured = capsys.readouterr()
    assert "session_id" in captured.err
    assert "abc-123" in captured.err
    assert "pod_logs" in captured.err
