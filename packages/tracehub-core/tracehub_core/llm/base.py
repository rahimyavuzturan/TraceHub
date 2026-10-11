"""LLM client interface and structured-output helper."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from tracehub_core.llm.types import ChatResponse, Message, ToolSpec
from tracehub_core.logging import get_logger

logger = get_logger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(?P<body>.*?)\s*```", re.DOTALL)

# Sent back to the model when its first structured answer failed validation.
_REPAIR_PROMPT = (
    "Verdiğin cevap beklenen şemaya uymuyor. Hata:\n{error}\n\n"
    "Sadece geçerli JSON döndür. Açıklama, yorum veya kod bloğu ekleme."
)


class LLMError(RuntimeError):
    """Raised when the model cannot be reached or returns an unusable answer."""


class LLMClient(ABC):
    """Provider agnostic chat interface."""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> ChatResponse:
        """Send a conversation and return the model's answer."""

    async def complete_structured(
        self,
        messages: list[Message],
        schema: type[ModelT],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ModelT:
        """Ask the model for JSON and validate it against ``schema``.

        One repair round is attempted when validation fails: the model is told
        what was wrong and asked again. A second failure raises ``LLMError`` -
        silently returning a half-valid object would be worse than failing.
        """
        conversation = list(messages)

        for attempt in (1, 2):
            response = await self.chat(
                conversation,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
            try:
                return schema.model_validate(extract_json(response.content))
            except (ValidationError, ValueError) as exc:
                logger.warning(
                    "structured_output_invalid",
                    attempt=attempt,
                    schema=schema.__name__,
                    error=str(exc)[:500],
                )
                if attempt == 2:
                    raise LLMError(
                        f"Model {schema.__name__} şemasına uygun cevap üretemedi."
                    ) from exc
                conversation = [
                    *conversation,
                    response.to_message(),
                    Message.user(_REPAIR_PROMPT.format(error=str(exc)[:1000])),
                ]

        raise AssertionError("unreachable")


def extract_json(text: str) -> object:
    """Parse JSON out of a model answer, tolerating markdown code fences."""
    candidate = text.strip()
    if not candidate:
        raise ValueError("Model boş cevap döndürdü.")

    fenced = _JSON_FENCE.search(candidate)
    if fenced:
        candidate = fenced.group("body").strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        # Some models prefix a sentence before the object; take the outermost braces.
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("Model cevabında JSON bulunamadı.") from exc
        return json.loads(candidate[start : end + 1])
