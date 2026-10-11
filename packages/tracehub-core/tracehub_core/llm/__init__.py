"""LLM and embedding access."""

from __future__ import annotations

from tracehub_core.config import LLMProvider, LLMSettings, settings
from tracehub_core.llm.base import LLMClient, LLMError, extract_json
from tracehub_core.llm.embedding import (
    EmbeddingClient,
    EmbeddingError,
    HashEmbedding,
    OpenAICompatibleEmbedding,
    build_embedding_client,
)
from tracehub_core.llm.mock import MockLLM, RecordedCall
from tracehub_core.llm.openai_compatible import OpenAICompatibleLLM
from tracehub_core.llm.types import ChatResponse, Message, ToolCall, ToolSpec, Usage

__all__ = [
    "ChatResponse",
    "EmbeddingClient",
    "EmbeddingError",
    "HashEmbedding",
    "LLMClient",
    "LLMError",
    "Message",
    "MockLLM",
    "OpenAICompatibleEmbedding",
    "OpenAICompatibleLLM",
    "RecordedCall",
    "ToolCall",
    "ToolSpec",
    "Usage",
    "build_embedding_client",
    "build_llm_client",
    "extract_json",
]


def build_llm_client(config: LLMSettings | None = None) -> LLMClient:
    """Create the LLM client selected by configuration.

    The ``mock`` provider returns an empty ``MockLLM``; tests are expected to
    build their own with scripted responses.
    """
    resolved = config or settings.llm
    if resolved.provider is LLMProvider.MOCK:
        return MockLLM()
    return OpenAICompatibleLLM(resolved)
