"""Tests for the HTTP layer and the MCP server wiring."""

from __future__ import annotations

import httpx
import pytest

from tracehub_mcp_common import ReadOnlyHttpClient, ReadOnlyViolationError
from tracehub_mcp_k8s.client import KubernetesApiError, KubernetesReadClient, safe_name
from tracehub_mcp_k8s.kubeconfig import ClusterConnection
from tracehub_mcp_k8s.server import TOOLS, build_server

from .conftest import K8sToolContext


def make_client(handler: httpx.MockTransport) -> KubernetesReadClient:
    connection = ClusterConnection(context="test-cluster", server="https://api.test.local:6443")
    http = ReadOnlyHttpClient(connection.server, transport=handler)
    return KubernetesReadClient(connection, http)


# --- transport ----------------------------------------------------------


async def test_every_request_is_a_get() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(200, json={"items": []})

    async with make_client(httpx.MockTransport(handler)) as client:
        await client.items("/api/v1/namespaces/mobile/pods")

    assert seen == ["GET"]


async def test_the_transport_refuses_to_write() -> None:
    """Pod deletion, exec and attach all need a verb this client cannot send."""
    http = ReadOnlyHttpClient("https://api.test.local:6443")
    with pytest.raises(ReadOnlyViolationError):
        await http.post("/api/v1/namespaces/mobile/pods/msube-web-7d9")
    await http.aclose()


async def test_none_parameters_are_dropped() -> None:
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url.query, "utf-8"))
        return httpx.Response(200, text="log")

    async with make_client(httpx.MockTransport(handler)) as client:
        await client.text("/api/v1/namespaces/mobile/pods/p/log", previous=None, tailLines=10)

    assert "previous" not in captured[0]
    assert "tailLines=10" in captured[0]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "Kimlik doğrulanamadı"),
        (403, "salt-okunur 'view' rolüne"),
        (404, "bulunamadı"),
    ],
)
async def test_api_errors_are_translated(status: int, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "forbidden"})

    async with make_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(KubernetesApiError, match=expected):
            await client.json("/api/v1/namespaces")


async def test_unexpected_status_includes_the_api_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "etcd unreachable"})

    async with make_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(KubernetesApiError, match="etcd unreachable"):
            await client.json("/api/v1/namespaces")


# --- name validation ----------------------------------------------------


@pytest.mark.parametrize("name", ["mobile", "msube-web-7d9", "a.b.c", "x1"])
def test_valid_names_pass(name: str) -> None:
    assert safe_name(name, kind="pod") == name


@pytest.mark.parametrize(
    "name",
    ["../etc", "UPPER", "with space", "-dash", "dash-", "semi;colon", "quote'", ""],
)
def test_invalid_names_are_rejected(name: str) -> None:
    with pytest.raises(KubernetesApiError):
        safe_name(name, kind="pod")


# --- server wiring ------------------------------------------------------


async def test_all_tools_are_registered(ctx: K8sToolContext) -> None:
    server = build_server(lambda: ctx)

    names = {tool.name for tool in await server.list_tools()}

    assert names == {tool.__name__ for tool in TOOLS}


async def test_tools_are_advertised_as_read_only(ctx: K8sToolContext) -> None:
    server = build_server(lambda: ctx)

    for tool in await server.list_tools():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False


async def test_context_is_hidden_from_the_tool_schema(ctx: K8sToolContext) -> None:
    """The model must not be able to pass its own policy or audit sink."""
    server = build_server(lambda: ctx)

    for tool in await server.list_tools():
        assert "ctx" not in tool.inputSchema.get("properties", {})


async def test_environment_is_required_on_every_tool(ctx: K8sToolContext) -> None:
    server = build_server(lambda: ctx)

    for tool in await server.list_tools():
        assert "environment" in tool.inputSchema.get("required", [])


async def test_descriptions_are_turkish(ctx: K8sToolContext) -> None:
    """The model picks a tool by its description, so it must be in Turkish."""
    server = build_server(lambda: ctx)

    for tool in await server.list_tools():
        assert tool.description is not None
        assert "salt okunur" in tool.description
