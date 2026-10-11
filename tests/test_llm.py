"""T0.4 - LLM client behaviour: mock, tool calls, structured output, retries."""

from __future__ import annotations

import httpx
import pytest
from pydantic import BaseModel, Field

from tracehub_core.config import LLMProvider, LLMSettings
from tracehub_core.llm import (
    ChatResponse,
    LLMError,
    Message,
    MockLLM,
    OpenAICompatibleLLM,
    ToolCall,
    ToolSpec,
    build_llm_client,
    extract_json,
)


class PlanStep(BaseModel):
    order: int
    tool: str
    rationale: str


class InvestigationPlan(BaseModel):
    summary: str
    steps: list[PlanStep] = Field(default_factory=list)


# --- MockLLM -----------------------------------------------------------------


async def test_mock_replays_scripted_answers_in_order() -> None:
    llm = MockLLM(responses=["birinci", "ikinci"])

    first = await llm.chat([Message.user("soru 1")])
    second = await llm.chat([Message.user("soru 2")])

    assert first.content == "birinci"
    assert second.content == "ikinci"
    assert llm.call_count == 2
    assert llm.calls[0].last_user_content == "soru 1"


async def test_mock_raises_turkish_error_when_script_is_exhausted() -> None:
    llm = MockLLM(responses=["tek cevap"])
    await llm.chat([Message.user("ilk")])

    with pytest.raises(LLMError, match="tükendi"):
        await llm.chat([Message.user("ikinci")])


async def test_mock_responder_can_branch_on_the_conversation() -> None:
    def responder(messages: list[Message], tools: list[ToolSpec] | None) -> ChatResponse:
        if "pod" in messages[-1].content:
            return ChatResponse(
                tool_calls=[ToolCall(id="c1", name="pod_logs", arguments={"environment": "test"})],
                finish_reason="tool_calls",
            )
        return ChatResponse(content="araç gerekmiyor")

    llm = MockLLM(responder=responder)

    tool_answer = await llm.chat([Message.user("pod loglarına bak")])
    plain_answer = await llm.chat([Message.user("merhaba")])

    assert tool_answer.wants_tools
    assert tool_answer.tool_calls[0].name == "pod_logs"
    assert not plain_answer.wants_tools


async def test_mock_records_offered_tools() -> None:
    tool = ToolSpec(
        name="pod_logs",
        description="Bir pod'un günlüklerini getirir (salt okunur).",
        parameters={"type": "object", "properties": {}},
    )
    llm = MockLLM(responses=["ok"])

    await llm.chat([Message.user("bak")], tools=[tool])

    recorded = llm.calls[0].tools
    assert recorded is not None
    assert recorded[0].name == "pod_logs"


def test_build_llm_client_honours_the_mock_provider() -> None:
    client = build_llm_client(LLMSettings(provider=LLMProvider.MOCK))
    assert isinstance(client, MockLLM)


# --- Structured output -------------------------------------------------------


async def test_structured_output_is_validated_against_the_schema() -> None:
    llm = MockLLM(
        responses=[
            '{"summary": "Pod loglarına bak", '
            '"steps": [{"order": 1, "tool": "pod_logs", "rationale": "hata arayacağız"}]}'
        ]
    )

    plan = await llm.complete_structured([Message.user("plan üret")], InvestigationPlan)

    assert plan.summary == "Pod loglarına bak"
    assert plan.steps[0].tool == "pod_logs"
    assert llm.calls[0].json_mode is True


async def test_structured_output_repairs_once_then_succeeds() -> None:
    llm = MockLLM(
        responses=[
            # "summary" zorunlu alani eksik -> dogrulama basarisiz olmali
            '{"steps": [{"order": 1, "tool": "kb_search", "rationale": "bilgi tabanı"}]}',
            '{"summary": "düzeltildi", "steps": [{"order": 1, "tool": "kb_search", '
            '"rationale": "önce bilgi tabanı"}]}',
        ]
    )

    plan = await llm.complete_structured([Message.user("plan üret")], InvestigationPlan)

    assert plan.summary == "düzeltildi"
    assert llm.call_count == 2, "geçersiz cevaptan sonra tam olarak bir düzeltme denenmeli"


async def test_repair_prompt_tells_the_model_what_was_wrong() -> None:
    llm = MockLLM(
        responses=[
            '{"steps": []}',
            '{"summary": "tamam", "steps": []}',
        ]
    )

    await llm.complete_structured([Message.user("plan üret")], InvestigationPlan)

    repair_conversation = llm.calls[1].messages
    assert repair_conversation[-1].role == "user"
    assert "summary" in repair_conversation[-1].content, "hata detayı modele iletilmeli"
    assert repair_conversation[-2].role == "assistant", "hatalı cevap bağlamda kalmalı"


async def test_structured_output_gives_up_after_the_repair_attempt() -> None:
    llm = MockLLM(responses=["kesinlikle json değil", "yine json değil"])

    with pytest.raises(LLMError, match="InvestigationPlan"):
        await llm.complete_structured([Message.user("plan üret")], InvestigationPlan)

    assert llm.call_count == 2, "sonsuz döngüye girmemeli"


@pytest.mark.parametrize(
    "raw",
    [
        '{"summary": "x", "steps": []}',
        '```json\n{"summary": "x", "steps": []}\n```',
        'İşte plan:\n{"summary": "x", "steps": []}\nUmarım yardımcı olur.',
    ],
)
def test_extract_json_tolerates_fences_and_prose(raw: str) -> None:
    assert extract_json(raw) == {"summary": "x", "steps": []}


def test_extract_json_rejects_answers_without_json() -> None:
    with pytest.raises(ValueError, match="JSON bulunamadı"):
        extract_json("burada hiç json yok")


# --- OpenAI compatible client ------------------------------------------------


def _client_with(handler: httpx.MockTransport) -> OpenAICompatibleLLM:
    client = OpenAICompatibleLLM(
        LLMSettings(provider=LLMProvider.OPENAI_COMPATIBLE, model="test-model")
    )
    client._client = httpx.AsyncClient(  # noqa: SLF001 - test seam
        base_url="http://model.test/v1",
        transport=handler,
    )
    return client


async def test_tool_calls_are_decoded_into_typed_objects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "pod_logs",
                                        "arguments": '{"environment": "test", "pod": "api-0"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    client = _client_with(httpx.MockTransport(handler))
    response = await client.chat([Message.user("logları getir")])

    assert response.wants_tools
    call = response.tool_calls[0]
    assert call.name == "pod_logs"
    assert call.arguments == {"environment": "test", "pod": "api-0"}
    assert response.usage.total_tokens == 15
    await client.aclose()


async def test_malformed_tool_arguments_do_not_crash_the_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {"name": "pod_logs", "arguments": "{bozuk"},
                                }
                            ]
                        },
                    }
                ]
            },
        )

    client = _client_with(httpx.MockTransport(handler))
    response = await client.chat([Message.user("logları getir")])

    assert response.tool_calls[0].arguments == {}
    await client.aclose()


async def test_timeouts_are_retried_then_succeed() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.TimeoutException("zaman asimi", request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "sonunda"}, "finish_reason": "stop"}]},
        )

    client = _client_with(httpx.MockTransport(handler))
    response = await client.chat([Message.user("dene")])

    assert response.content == "sonunda"
    assert attempts == 3
    await client.aclose()


async def test_server_errors_surface_as_turkish_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="model yuklenemedi")

    client = _client_with(httpx.MockTransport(handler))

    with pytest.raises(LLMError, match="500"):
        await client.chat([Message.user("dene")])
    await client.aclose()


async def test_empty_choices_are_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = _client_with(httpx.MockTransport(handler))

    with pytest.raises(LLMError, match="boş cevap"):
        await client.chat([Message.user("dene")])
    await client.aclose()


async def test_request_payload_carries_tools_and_json_mode() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as json_module

        captured.update(json_module.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]},
        )

    tool = ToolSpec(
        name="kb_search",
        description="Bilgi tabanında arama yapar.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
    )
    client = _client_with(httpx.MockTransport(handler))
    await client.chat([Message.user("ara")], tools=[tool], json_mode=True)

    assert captured["response_format"] == {"type": "json_object"}
    assert captured["tool_choice"] == "auto"
    tools = captured["tools"]
    assert isinstance(tools, list)
    assert tools[0]["function"]["name"] == "kb_search"
    await client.aclose()


async def test_api_key_is_sent_but_never_shown_in_settings_repr() -> None:
    config = LLMSettings(
        provider=LLMProvider.OPENAI_COMPATIBLE,
        api_key="gizli-anahtar",  # type: ignore[arg-type]
    )
    client = OpenAICompatibleLLM(config)

    assert client._headers()["Authorization"] == "Bearer gizli-anahtar"  # noqa: SLF001
    assert "gizli-anahtar" not in repr(config)
    await client.aclose()


def test_tool_spec_serialises_to_openai_schema() -> None:
    tool = ToolSpec(
        name="pod_logs",
        description="Bir pod'un günlüklerini getirir (salt okunur).",
        parameters={"type": "object", "properties": {"pod": {"type": "string"}}},
    )

    schema = tool.to_openai_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "pod_logs"
    assert "salt okunur" in schema["function"]["description"]
