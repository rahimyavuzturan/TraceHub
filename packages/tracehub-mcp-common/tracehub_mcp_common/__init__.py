"""TraceHub MCP common layer.

Shared read-only infrastructure for every MCP server: the ``@readonly_tool``
guard, the access policy, secret redaction, output trimming and the read-only
HTTP client.
"""

from __future__ import annotations

from .context import (
    AuditEvent,
    AuditSink,
    LoggingAuditSink,
    MemoryAuditSink,
    ToolBudgetState,
    ToolContext,
)
from .guard import FORBIDDEN_PREFIXES, ReadOnlyToolError, ToolBudget, readonly_tool
from .http import (
    ALLOWED_METHODS,
    SEARCH_POST_SUFFIXES,
    ReadOnlyHttpClient,
    ReadOnlyViolationError,
)
from .policy import AllowDeny, Environment, Policy, PolicyError, get_policy, load_policy
from .redaction import redact, redact_detailed, redact_mapping
from .summarize import format_table, summarize_output

__all__ = [
    "ALLOWED_METHODS",
    "FORBIDDEN_PREFIXES",
    "SEARCH_POST_SUFFIXES",
    "AllowDeny",
    "AuditEvent",
    "AuditSink",
    "Environment",
    "LoggingAuditSink",
    "MemoryAuditSink",
    "Policy",
    "PolicyError",
    "ReadOnlyHttpClient",
    "ReadOnlyToolError",
    "ReadOnlyViolationError",
    "ToolBudget",
    "ToolBudgetState",
    "ToolContext",
    "format_table",
    "get_policy",
    "load_policy",
    "readonly_tool",
    "redact",
    "redact_detailed",
    "redact_mapping",
    "summarize_output",
]
