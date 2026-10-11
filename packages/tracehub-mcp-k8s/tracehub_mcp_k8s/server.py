"""MCP server exposing the read-only Kubernetes tools over STDIO.

Nothing is written to stdout except the JSON-RPC protocol itself -- logging
goes to stderr, which is why ``print()`` is banned in this package.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from tracehub_core.logging import configure_logging, get_logger
from tracehub_mcp_common import get_policy

from .client import ClusterResolver
from .tools import (
    K8sToolContext,
    describe_pod,
    deployment_status,
    list_events,
    list_namespaces,
    list_pods,
    pod_logs,
    previous_pod_logs,
    resource_usage,
)

logger = get_logger(__name__)

SERVER_NAME = "tracehub-k8s"

#: Advertised to any MCP client so the model knows these calls are safe.
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)

TOOLS: tuple[Callable[..., Awaitable[str]], ...] = (
    list_namespaces,
    list_pods,
    describe_pod,
    pod_logs,
    previous_pod_logs,
    list_events,
    deployment_status,
    resource_usage,
)


def build_server(context_factory: Callable[[], K8sToolContext] | None = None) -> MCPServer:
    """Register every read-only tool on a fresh MCP server.

    Args:
        context_factory: Produces the :class:`K8sToolContext` for a call.
            Tests pass a factory backed by a fake cluster.
    """
    factory = context_factory or _default_context
    server: MCPServer = MCPServer(
        name=SERVER_NAME,
        instructions=(
            "Kubernetes kumelerine SALT OKUNUR erisim saglar. "
            "Hicbir arac degisiklik yapmaz; degisiklik gerekiyorsa kullaniciya onerilir."
        ),
    )

    for tool in TOOLS:
        server.add_tool(_without_context(tool, factory), annotations=READ_ONLY)

    logger.info("mcp_server_ready", server=SERVER_NAME, tools=len(TOOLS))
    return server


def _without_context(
    tool: Callable[..., Awaitable[str]],
    factory: Callable[[], K8sToolContext],
) -> Callable[..., Awaitable[str]]:
    """Hide the ``ctx`` parameter from the MCP schema and inject it at call time.

    The model should only see the diagnostic arguments; policy, audit and
    budget are ours to supply.
    """
    signature = inspect.signature(tool)
    visible = [
        parameter for name, parameter in signature.parameters.items() if name != "ctx"
    ]

    @functools.wraps(tool)
    async def adapter(**kwargs: Any) -> str:
        return await tool(factory(), **kwargs)

    adapter.__signature__ = signature.replace(parameters=visible)  # type: ignore[attr-defined]
    return adapter


def _default_context() -> K8sToolContext:
    return K8sToolContext(policy=get_policy(), clusters=ClusterResolver())


def main() -> None:
    """Entry point for ``tracehub-mcp-k8s``."""
    configure_logging()
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
