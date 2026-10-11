"""Embedding clients.

Two providers:

* ``openai_compatible`` - the real bge-m3 deployment (TEI or vLLM).
* ``hash`` - a deterministic, dependency-free vectoriser for development and CI.

The hash provider uses the hashing trick over word tokens, so texts that share
vocabulary really do land close together. That is enough to develop and test the
hybrid search pipeline without a GPU, while staying fully reproducible.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from tracehub_core.config import EmbeddingProvider, EmbeddingSettings, settings
from tracehub_core.logging import get_logger

logger = get_logger(__name__)

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
_RETRYABLE = (httpx.TimeoutException, httpx.NetworkError)


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be produced."""


class EmbeddingClient(ABC):
    """Turns text into vectors."""

    def __init__(self, config: EmbeddingSettings | None = None) -> None:
        self._config = config or settings.embedding

    @property
    def dimensions(self) -> int:
        return self._config.dimensions

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, preserving input order."""

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]


class HashEmbedding(EmbeddingClient):
    """Deterministic local embedding - development and tests only."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorise(text) for text in texts]

    def _vectorise(self, text: str) -> list[float]:
        dimensions = self.dimensions
        vector = [0.0] * dimensions

        for token in _TOKEN_PATTERN.findall(text.casefold()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


class OpenAICompatibleEmbedding(EmbeddingClient):
    """Talks to any server exposing ``POST /embeddings``."""

    def __init__(self, config: EmbeddingSettings | None = None) -> None:
        super().__init__(config)
        headers = {"Content-Type": "application/json"}
        api_key = self._config.api_key.get_secret_value()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=self._config.base_url.rstrip("/"),
            timeout=self._config.timeout_seconds,
            headers=headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        batch_size = self._config.batch_size
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors.extend(await self._embed_batch(batch))
        return vectors

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"model": self._config.model, "input": batch}
        try:
            response = await self._client.post("/embeddings", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("embedding_http_error", status=exc.response.status_code)
            raise EmbeddingError(f"Gömme servisi {exc.response.status_code} döndürdü.") from exc
        except _RETRYABLE:
            raise
        except httpx.HTTPError as exc:
            raise EmbeddingError("Gömme servisine ulaşılamadı.") from exc

        data = response.json().get("data") or []
        if len(data) != len(batch):
            raise EmbeddingError(
                f"Gömme servisi {len(batch)} metin için {len(data)} vektör döndürdü."
            )

        # The API does not guarantee ordering, but it does return an index.
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        vectors = [[float(value) for value in item["embedding"]] for item in ordered]

        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingError(
                    f"Beklenen boyut {self.dimensions}, gelen {len(vector)}. "
                    "TRACEHUB_EMBEDDING__DIMENSIONS ayarını kontrol edin."
                )
        return vectors


def build_embedding_client(config: EmbeddingSettings | None = None) -> EmbeddingClient:
    """Create the embedding client selected by configuration."""
    resolved = config or settings.embedding
    if resolved.provider is EmbeddingProvider.HASH:
        return HashEmbedding(resolved)
    return OpenAICompatibleEmbedding(resolved)
