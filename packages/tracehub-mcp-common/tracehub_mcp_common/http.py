"""HTTP client that can only read.

This is defence layer two for every REST-based integration (Elasticsearch,
Grafana, Azure DevOps, NetScaler). The client physically refuses to issue a
state-changing verb.

The single exception is Elasticsearch ``_search`` / ``_count``, which require a
request body and therefore must be sent as ``POST``. That exception is
allowlisted here explicitly and nowhere else.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Final, Self
from urllib.parse import urljoin, urlsplit

import httpx

from tracehub_core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_METHODS: Final = frozenset({"GET", "HEAD"})

#: Elasticsearch endpoints that need a POST body but change nothing.
SEARCH_POST_SUFFIXES: Final = ("/_search", "/_count", "/_msearch", "/_field_caps")

DEFAULT_TIMEOUT: Final = 30.0


class ReadOnlyViolationError(RuntimeError):
    """Raised when someone tries to send a state-changing request."""


class ReadOnlyHttpClient:
    """An ``httpx`` wrapper restricted to read-only traffic.

    Args:
        base_url: Target root. All request paths are resolved against it and
            must stay on the same host (SSRF guard).
        headers: Static headers, e.g. authentication.
        timeout: Per-request timeout in seconds.
        verify: TLS verification. Pass a CA bundle path for internal PKI;
            never disable it.
        cert: Client certificate as ``(cert_path, key_path)`` when the target
            authenticates with mTLS.
        transport: Optional transport override. Tests inject a mock here.
    """

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        verify: bool | str = True,
        cert: tuple[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._host = urlsplit(self._base_url).netloc
        self._client = httpx.AsyncClient(
            headers=headers or {},
            timeout=timeout,
            verify=verify,
            cert=cert,
            follow_redirects=False,
            transport=transport,
        )

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
        await self._client.aclose()

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Issue a GET request."""
        return await self._request("GET", path, params=params)

    async def head(self, path: str) -> httpx.Response:
        """Issue a HEAD request."""
        return await self._request("HEAD", path)

    async def search(
        self,
        path: str,
        *,
        body: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Issue the allowlisted Elasticsearch search POST.

        Raises:
            ReadOnlyViolationError: If ``path`` is not a search endpoint.
        """
        if not _is_search_endpoint(path):
            raise ReadOnlyViolationError(
                f"POST yalnızca Elasticsearch arama uç noktalarında kullanılabilir. "
                f"İzin verilen sonlar: {', '.join(SEARCH_POST_SUFFIXES)}. Verilen: {path}"
            )
        return await self._request("POST", path, params=params, json=body)

    async def post(self, *args: object, **kwargs: object) -> httpx.Response:
        """Always fails. TraceHub does not write to target systems."""
        raise ReadOnlyViolationError(
            "TraceHub salt okunurdur: POST isteği gönderilemez. "
            "Elasticsearch araması için search() kullanın."
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if method not in ALLOWED_METHODS and not (method == "POST" and _is_search_endpoint(path)):
            raise ReadOnlyViolationError(f"'{method}' HTTP fiili salt okunur istemcide yasaktır.")

        url = self._resolve(path)
        response = await self._client.request(method, url, params=params, json=json)
        logger.debug(
            "http_request",
            method=method,
            host=self._host,
            path=urlsplit(url).path,
            status=response.status_code,
        )
        return response

    def _resolve(self, path: str) -> str:
        """Join ``path`` onto the base URL and refuse to leave the host."""
        url = urljoin(self._base_url, path.lstrip("/"))
        if urlsplit(url).netloc != self._host:
            raise ReadOnlyViolationError(
                f"İstek hedefi yapılandırılmış sunucunun dışına çıkıyor: {url}"
            )
        return url


def _is_search_endpoint(path: str) -> bool:
    clean = urlsplit(path).path.rstrip("/")
    return clean.endswith(SEARCH_POST_SUFFIXES)
