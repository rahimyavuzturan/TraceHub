"""Read-only access to the Kubernetes REST API.

Every call goes through :class:`~tracehub_mcp_common.http.ReadOnlyHttpClient`,
so the transport itself rejects anything other than ``GET``/``HEAD``. Pod
``exec``, ``attach`` and port forwarding all require an upgraded POST, which
this client cannot issue.
"""

from __future__ import annotations

import re
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx

from tracehub_core.config import settings
from tracehub_mcp_common import Policy, ReadOnlyHttpClient

from .kubeconfig import ClusterConnection, load_connection

#: RFC 1123 subdomain, the shape every Kubernetes object name must have.
NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")


class KubernetesApiError(RuntimeError):
    """The API server answered with an error we should show the user."""


def safe_name(value: str, *, kind: str) -> str:
    """Validate and URL-encode an object name before it enters a request path.

    Names arrive from the model, so they are untrusted input. Rejecting
    anything that is not a legal Kubernetes name closes off path traversal and
    query smuggling.
    """
    candidate = value.strip()
    if not NAME_PATTERN.match(candidate):
        raise KubernetesApiError(
            f"'{value}' geçerli bir Kubernetes {kind} adı değil "
            "(küçük harf, rakam, '-' ve '.' kullanılabilir)."
        )
    return quote(candidate, safe="")


class KubernetesReadClient:
    """Thin read-only wrapper around one cluster's API server."""

    def __init__(self, connection: ClusterConnection, http: ReadOnlyHttpClient) -> None:
        self.connection = connection
        self._http = http

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def json(self, path: str, **params: Any) -> dict[str, Any]:
        """GET a path and return the decoded JSON object."""
        response = await self._http.get(path, params=_clean(params))
        _raise_for_status(response, path)
        payload = response.json()
        if not isinstance(payload, dict):
            raise KubernetesApiError(f"Beklenmeyen API yanıtı: {path}")
        return payload

    async def items(self, path: str, **params: Any) -> list[dict[str, Any]]:
        """GET a list endpoint and return its ``items``."""
        payload = await self.json(path, **params)
        items = payload.get("items")
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    async def text(self, path: str, **params: Any) -> str:
        """GET a path that returns plain text, such as container logs."""
        response = await self._http.get(path, params=_clean(params))
        _raise_for_status(response, path)
        return response.text


class ClusterResolver:
    """Opens a read-only client for a logical environment.

    Held on the tool context so tests can substitute a fake without touching
    module-level state.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def open(self, environment: str, policy: Policy) -> KubernetesReadClient:
        """Resolve ``environment`` to its kubeconfig context and connect."""
        context = policy.environment(environment).k8s_context
        if not context:
            raise KubernetesApiError(
                f"'{environment}' ortamı için kubeconfig context'i tanımlı değil "
                "(config/environments.yaml içindeki k8s_context alanı)."
            )

        connection = load_connection(settings.kubernetes.resolved_kubeconfig(), context)
        http = ReadOnlyHttpClient(
            connection.server,
            headers=connection.headers,
            timeout=settings.kubernetes.timeout_seconds,
            verify=connection.verify,
            cert=connection.cert,
            transport=self._transport,
        )
        return KubernetesReadClient(connection, http)


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def _raise_for_status(response: httpx.Response, path: str) -> None:
    if response.status_code < 400:
        return

    reason = {
        401: "Kimlik doğrulanamadı: token geçersiz veya süresi dolmuş.",
        403: "Yetki yok. Servis hesabı salt-okunur 'view' rolüne sahip mi?",
        404: "Kaynak bulunamadı.",
    }.get(response.status_code)

    if reason is None:
        message = _api_message(response) or response.reason_phrase
        reason = f"API sunucusu {response.status_code} döndürdü: {message}"

    raise KubernetesApiError(f"{reason} (istek: {path})")


def _api_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    return str(payload.get("message", "")) if isinstance(payload, dict) else ""
