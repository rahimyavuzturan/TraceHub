"""OpenAI compatible chat client (vLLM, TGI, ...)."""

from __future__ import annotations

import json
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tracehub_core.config import LLMSettings, settings
from tracehub_core.llm.base import LLMClient, LLMError
from tracehub_core.llm.types import ChatResponse, Message, ToolCall, ToolSpec, Usage
from tracehub_core.logging import get_logger

logger = get_logger(__name__)

# Network blips and 5xx are worth retrying; a 400 means our payload is wrong.
_RETRYABLE = (httpx.TimeoutException, httpx.NetworkError)


class OpenAICompatibleLLM(LLMClient):
    """Talks to any server exposing ``POST /chat/completions``."""

    def __init__(self, config: LLMSettings | None = None) -> None:
        self._config = config or settings.llm
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url.rstrip("/"),
            timeout=self._config.timeout_seconds,
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = self._config.api_key.get_secret_value()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [_encode_message(message) for message in messages],
            "temperature": self._config.temperature if temperature is None else temperature,
            "max_tokens": self._config.max_tokens if max_tokens is None else max_tokens,
        }
        if tools:
            payload["tools"] = [tool.to_openai_schema() for tool in tools]
            payload["tool_choice"] = "auto"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        data = await self._post(payload)
        return _decode_response(data, fallback_model=self._config.model)

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "llm_http_error",
                status=exc.response.status_code,
                body=exc.response.text[:500],
            )
            raise LLMError(f"Dil modeli {exc.response.status_code} döndürdü.") from exc
        except _RETRYABLE:
            raise
        except httpx.HTTPError as exc:
            raise LLMError("Dil modeline ulaşılamadı.") from exc

        body: dict[str, Any] = response.json()
        return body


def _encode_message(message: Message) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    if message.name:
        payload["name"] = message.name
    return payload


def _decode_response(data: dict[str, Any], *, fallback_model: str) -> ChatResponse:
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("Dil modeli boş cevap döndürdü.")

    choice = choices[0]
    message = choice.get("message") or {}
    usage = data.get("usage") or {}

    return ChatResponse(
        content=message.get("content") or "",
        tool_calls=[_decode_tool_call(raw) for raw in message.get("tool_calls") or []],
        finish_reason=choice.get("finish_reason") or "stop",
        usage=Usage(
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        ),
        model=data.get("model") or fallback_model,
    )


def _decode_tool_call(raw: dict[str, Any]) -> ToolCall:
    function = raw.get("function") or {}
    raw_arguments = function.get("arguments") or "{}"
    try:
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
    except json.JSONDecodeError:
        logger.warning("tool_call_arguments_unparsable", tool=function.get("name"))
        arguments = {}

    return ToolCall(
        id=raw.get("id") or "call_0",
        name=function.get("name") or "",
        arguments=arguments if isinstance(arguments, dict) else {},
    )
