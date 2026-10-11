"""Deterministic mock LLM for tests and GPU-less development.

CI has no model server, so every agent test runs against this client. It also
records the conversations it received, which is how graph tests assert that a
node sent the right prompt or that no tool ran before approval.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from tracehub_core.llm.base import LLMClient, LLMError
from tracehub_core.llm.types import ChatResponse, Message, ToolSpec, Usage

Responder = Callable[[list[Message], list[ToolSpec] | None], ChatResponse | str]


@dataclass
class RecordedCall:
    """One captured request, for assertions in tests."""

    messages: list[Message]
    tools: list[ToolSpec] | None
    json_mode: bool

    @property
    def last_user_content(self) -> str:
        for message in reversed(self.messages):
            if message.role == "user":
                return message.content
        return ""


@dataclass
class MockLLM(LLMClient):
    """Replays scripted answers in order, or delegates to a responder callable.

    ``responses`` accepts plain strings (turned into content-only answers) or
    full ``ChatResponse`` objects when tool calls need to be simulated.
    """

    responses: Sequence[ChatResponse | str] = field(default_factory=list)
    responder: Responder | None = None
    calls: list[RecordedCall] = field(default_factory=list, init=False)
    _cursor: int = field(default=0, init=False)

    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> ChatResponse:
        self.calls.append(RecordedCall(messages=list(messages), tools=tools, json_mode=json_mode))

        if self.responder is not None:
            return _coerce(self.responder(messages, tools))

        if self._cursor >= len(self.responses):
            raise LLMError(
                f"MockLLM cevapları tükendi ({len(self.responses)} tanımlı, "
                f"{self._cursor + 1}. çağrı yapıldı)."
            )

        answer = self.responses[self._cursor]
        self._cursor += 1
        return _coerce(answer)

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def reset(self) -> None:
        self.calls.clear()
        self._cursor = 0


def _coerce(answer: ChatResponse | str) -> ChatResponse:
    if isinstance(answer, ChatResponse):
        return answer
    return ChatResponse(
        content=answer,
        model="mock",
        usage=Usage(prompt_tokens=0, completion_tokens=len(answer.split())),
    )
