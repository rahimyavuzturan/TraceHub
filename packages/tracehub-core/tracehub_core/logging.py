"""Structured logging setup.

Logs always go to stderr so that STDIO-based MCP servers keep stdout clean for
the JSON-RPC protocol.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from tracehub_core.config import settings

_configured = False


def configure_logging(*, force: bool = False) -> None:
    global _configured
    if _configured and not force:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        force=True,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
