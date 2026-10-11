"""Execution context handed to every MCP tool.

A tool never reaches out to configuration, logging or the audit trail on its
own. It receives a :class:`ToolContext` as its first parameter and goes through
that, which keeps policy enforcement and auditing impossible to skip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

import structlog

from tracehub_core.logging import get_logger

from .policy import Policy, PolicyError, get_policy


@dataclass(frozen=True)
class AuditEvent:
    """One tool invocation, recorded whether it succeeded or not."""

    event_id: str
    session_id: str
    actor: str
    tool: str
    category: str
    environment: str | None
    parameters: dict[str, Any]
    started_at: datetime
    duration_ms: int
    ok: bool
    error: str | None = None
    is_production: bool = False


class AuditSink(Protocol):
    """Destination for audit events."""

    async def write(self, event: AuditEvent) -> None: ...


class LoggingAuditSink:
    """Writes audit events to the structured log.

    The database-backed sink arrives with the persistence layer; until then the
    log is the audit trail.
    """

    def __init__(self) -> None:
        self._logger = get_logger("tracehub.audit")

    async def write(self, event: AuditEvent) -> None:
        self._logger.info(
            "tool_call",
            event_id=event.event_id,
            session_id=event.session_id,
            actor=event.actor,
            tool=event.tool,
            category=event.category,
            environment=event.environment,
            is_production=event.is_production,
            duration_ms=event.duration_ms,
            ok=event.ok,
            error=event.error,
            parameters=event.parameters,
        )


class MemoryAuditSink:
    """Collects audit events in memory. Used by tests."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def write(self, event: AuditEvent) -> None:
        self.events.append(event)


@dataclass
class ToolBudgetState:
    """Tracks how much investigation a single session has spent."""

    max_calls: int = 40
    spent_calls: int = 0
    spent_cost: int = 0
    max_cost: int = 120

    def charge(self, cost: int) -> None:
        """Record one tool call.

        Raises:
            PolicyError: When the session budget is exhausted.
        """
        if self.spent_calls >= self.max_calls:
            raise PolicyError(
                f"Araştırma bütçesi doldu: {self.max_calls} araç çağrısı sınırına ulaşıldı. "
                "Eldeki bulgularla rapor üretin."
            )
        if self.spent_cost + cost > self.max_cost:
            raise PolicyError("Araştırma maliyeti bütçesi doldu. Eldeki bulgularla rapor üretin.")
        self.spent_calls += 1
        self.spent_cost += cost


@dataclass
class ToolContext:
    """What a tool is allowed to know and do."""

    session_id: str = field(default_factory=lambda: str(uuid4()))
    actor: str = "system"
    policy: Policy = field(default_factory=get_policy)
    audit: AuditSink = field(default_factory=LoggingAuditSink)
    budget: ToolBudgetState = field(default_factory=ToolBudgetState)
    logger: structlog.stdlib.BoundLogger = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.logger = get_logger("tracehub.tool").bind(
            session_id=self.session_id,
            actor=self.actor,
        )

    async def record(self, event: AuditEvent) -> None:
        await self.audit.write(event)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)
