"""T0.4 - embedding clients: deterministic hash provider and the HTTP provider."""

from __future__ import annotations

import math

import httpx
import pytest

from tracehub_core.config import EmbeddingProvider, EmbeddingSettings
from tracehub_core.llm import (
    EmbeddingError,
    HashEmbedding,
    OpenAICompatibleEmbedding,
    build_embedding_client,
)


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _hash_client(dimensions: int = 64) -> HashEmbedding:
    return HashEmbedding(EmbeddingSettings(provider=EmbeddingProvider.HASH, dimensions=dimensions))


# --- Hash provider -----------------------------------------------------------


async def test_hash_embedding_is_deterministic() -> None:
    client = _hash_client()

    first = await client.embed_one("mobil şube arızası")
    second = await client.embed_one("mobil şube arızası")

    assert first == second


async def test_hash_embedding_respects_configured_dimensions() -> None:
    client = _hash_client(dimensions=128)

    vector = await client.embed_one("msube")

    assert len(vector) == 128
    assert client.dimensions == 128


async def test_hash_embedding_vectors_are_normalised() -> None:
    client = _hash_client()

    vector = await client.embed_one("CrashLoopBackOff ConfigMap hatası")

    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)


async def test_hash_embedding_keeps_shared_vocabulary_close() -> None:
    """Shared words must score higher than unrelated text - search dev depends on it."""
    client = _hash_client(dimensions=512)

    query, related, unrelated = await client.embed(
        [
            "mobil şube pod yeniden başlıyor",
            "mobil şube pod CrashLoopBackOff durumunda",
            "azure devops repo silme onay süreci",
        ]
    )

    assert _cosine(query, related) > _cosine(query, unrelated)


async def test_hash_embedding_is_case_insensitive() -> None:
    client = _hash_client()

    lower, upper = await client.embed(["msube web", "MSUBE WEB"])

    assert lower == upper


async def test_hash_embedding_handles_empty_text() -> None:
    client = _hash_client()

    vector = await client.embed_one("")

    assert len(vector) == client.dimensions
    assert all(value == 0.0 for value in vector)


async def test_hash_embedding_preserves_batch_order() -> None:
    client = _hash_client()

    batch = await client.embed(["bir", "iki", "uc"])
    individually = [await client.embed_one(text) for text in ("bir", "iki", "uc")]

    assert batch == individually


def test_build_embedding_client_honours_the_hash_provider() -> None:
    client = build_embedding_client(
        EmbeddingSettings(provider=EmbeddingProvider.HASH, dimensions=8)
    )
    assert isinstance(client, HashEmbedding)


# --- HTTP provider -----------------------------------------------------------


def _http_client(handler: httpx.MockTransport, *, dimensions: int = 4) -> OpenAICompatibleEmbedding:
    client = OpenAICompatibleEmbedding(
        EmbeddingSettings(
            provider=EmbeddingProvider.OPENAI_COMPATIBLE,
            dimensions=dimensions,
            batch_size=2,
        )
    )
    client._client = httpx.AsyncClient(  # noqa: SLF001 - test seam
        base_url="http://tei.test/v1",
        transport=handler,
    )
    return client


async def test_http_embedding_reorders_by_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [1.0, 1.0, 1.0, 1.0]},
                    {"index": 0, "embedding": [0.0, 0.0, 0.0, 0.0]},
                ]
            },
        )

    client = _http_client(httpx.MockTransport(handler))
    vectors = await client.embed(["ilk", "ikinci"])

    assert vectors[0] == [0.0, 0.0, 0.0, 0.0]
    assert vectors[1] == [1.0, 1.0, 1.0, 1.0]
    await client.aclose()


async def test_http_embedding_splits_into_batches() -> None:
    seen_batches: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as json_module

        payload = json_module.loads(request.content)
        seen_batches.append(len(payload["input"]))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [0.0, 0.0, 0.0, 0.0]}
                    for i in range(len(payload["input"]))
                ]
            },
        )

    client = _http_client(httpx.MockTransport(handler))
    vectors = await client.embed(["a", "b", "c", "d", "e"])

    assert len(vectors) == 5
    assert seen_batches == [2, 2, 1], "batch_size=2 ayarına uyulmalı"
    await client.aclose()


async def test_http_embedding_rejects_dimension_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]})

    client = _http_client(httpx.MockTransport(handler), dimensions=1024)

    with pytest.raises(EmbeddingError, match="Beklenen boyut 1024"):
        await client.embed(["tek metin"])
    await client.aclose()


async def test_http_embedding_rejects_count_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0] * 4}]})

    client = _http_client(httpx.MockTransport(handler))

    with pytest.raises(EmbeddingError, match="2 metin için 1 vektör"):
        await client.embed(["ilk", "ikinci"])
    await client.aclose()


async def test_http_embedding_surfaces_server_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="model yukleniyor")

    client = _http_client(httpx.MockTransport(handler))

    with pytest.raises(EmbeddingError, match="503"):
        await client.embed(["metin"])
    await client.aclose()


async def test_http_embedding_retries_timeouts() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.TimeoutException("zaman asimi", request=request)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5] * 4}]})

    client = _http_client(httpx.MockTransport(handler))
    vectors = await client.embed(["metin"])

    assert vectors == [[0.5, 0.5, 0.5, 0.5]]
    assert attempts == 2
    await client.aclose()


async def test_http_embedding_short_circuits_on_empty_input() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - not called
        raise AssertionError("bos girdi icin istek atilmamali")

    client = _http_client(httpx.MockTransport(handler))

    assert await client.embed([]) == []
    await client.aclose()
