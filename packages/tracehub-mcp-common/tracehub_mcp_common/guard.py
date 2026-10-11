"""The ``@readonly_tool`` decorator: defence layer two.

Wraps every MCP tool so that a tool author cannot forget the shared rules:

* the function name must not look like a write operation (checked at import time),
* the first parameter must be ``ctx: ToolContext``,
* the session budget is charged before the call,
* the return value is redacted and trimmed before the model ever sees it,
* an audit record is written whether the call succeeds or fails.
"""

from __future__ import annotations

import functools
import inspect
import time
from collections.abc import Awaitable, Callable
from enum import IntEnum
from typing import Any, Final, ParamSpec, TypeVar
from uuid import uuid4

from .context import AuditEvent, ToolContext
from .policy import PolicyError
from .redaction import redact, redact_mapping
from .summarize import summarize_output

P = ParamSpec("P")
R = TypeVar("R")

#: Name prefixes that imply a state change. A tool may not use them.
FORBIDDEN_PREFIXES: Final = (
    "create_",
    "update_",
    "patch_",
    "delete_",
    "remove_",
    "apply_",
    "put_",
    "post_",
    "set_",
    "restart_",
    "scale_",
    "exec_",
    "drain_",
    "cordon_",
    "uncordon_",
    "rollout_",
    "write_",
    "edit_",
    "kill_",
    "evict_",
    "attach_",
    "port_forward_",
)


class ToolBudget(IntEnum):
    """Relative cost of a tool call, charged against the session budget."""

    CHEAP = 1
    MODERATE = 3
    EXPENSIVE = 8


class ReadOnlyToolError(RuntimeError):
    """Raised at import time when a tool definition breaks the read-only contract."""


def readonly_tool(
    *,
    category: str,
    cost: ToolBudget = ToolBudget.CHEAP,
    max_chars: int = 4000,
) -> Callable[[Callable[P, Awaitable[str]]], Callable[P, Awaitable[str]]]:
    """Mark an async function as a read-only MCP tool.

    Args:
        category: Integration name, e.g. ``"k8s"``, ``"elastic"``, ``"grafana"``.
        cost: How expensive the call is for the session budget.
        max_chars: Upper bound on the text returned to the model.
    """

    def decorator(func: Callable[P, Awaitable[str]]) -> Callable[P, Awaitable[str]]:
        _validate_definition(func)
        signature = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> str:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()

            ctx = bound.arguments["ctx"]
            if not isinstance(ctx, ToolContext):
                raise ReadOnlyToolError(
                    f"{func.__name__}: ilk parametre bir ToolContext örneği olmalı."
                )

            environment = bound.arguments.get("environment")
            parameters = {name: value for name, value in bound.arguments.items() if name != "ctx"}

            started_at = ctx.now()
            start = time.perf_counter()
            error: str | None = None
            try:
                ctx.budget.charge(int(cost))
                result = await func(*args, **kwargs)
                output = summarize_output(redact(result), max_chars=max_chars)
            except PolicyError as exc:
                # A policy refusal is an expected outcome, not a crash: the model
                # should read it and pick a different route.
                error = str(exc)
                output = f"Erişim reddedildi: {exc}"
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                await ctx.record(
                    AuditEvent(
                        event_id=str(uuid4()),
                        session_id=ctx.session_id,
                        actor=ctx.actor,
                        tool=func.__name__,
                        category=category,
                        environment=str(environment) if environment else None,
                        parameters=redact_mapping(parameters),
                        started_at=started_at,
                        duration_ms=int((time.perf_counter() - start) * 1000),
                        ok=error is None,
                        error=error,
                        is_production=_is_production(ctx, environment),
                    )
                )
            return output

        wrapper.__tracehub_readonly__ = True  # type: ignore[attr-defined]
        wrapper.__tracehub_category__ = category  # type: ignore[attr-defined]
        wrapper.__tracehub_cost__ = int(cost)  # type: ignore[attr-defined]
        return wrapper

    return decorator


def _validate_definition(func: Callable[..., Any]) -> None:
    """Reject a tool definition that breaks the contract, at import time."""
    name = func.__name__
    lowered = name.casefold()

    if lowered.startswith(FORBIDDEN_PREFIXES):
        raise ReadOnlyToolError(
            f"'{name}' durum değiştiren bir isim taşıyor. "
            "TraceHub araçları salt okunurdur; yasaklı önekler: "
            f"{', '.join(FORBIDDEN_PREFIXES)}"
        )

    if not inspect.iscoroutinefunction(func):
        raise ReadOnlyToolError(f"'{name}' async tanımlanmalı.")

    parameters = list(inspect.signature(func).parameters)
    if not parameters or parameters[0] != "ctx":
        raise ReadOnlyToolError(f"'{name}' ilk parametresi 'ctx: ToolContext' olmalı.")

    if not (func.__doc__ or "").strip():
        raise ReadOnlyToolError(
            f"'{name}' için Türkçe docstring zorunlu: model aracı bu metinden seçer."
        )


def _is_production(ctx: ToolContext, environment: object) -> bool:
    if not isinstance(environment, str):
        return False
    try:
        return ctx.policy.is_production(environment)
    except PolicyError:
        return False
