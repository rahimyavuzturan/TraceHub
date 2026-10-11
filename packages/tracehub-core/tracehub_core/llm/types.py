"""Shared data types for the LLM layer.

These models are provider agnostic: the OpenAI compatible client and the mock
client both speak this vocabulary, so the rest of the codebase never depends on
a vendor specific payload shape.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class Message(BaseModel):
    """A single turn in a conversation."""

    role: Role
    content: str = ""
    # Set on assistant turns that requested tools, mirrored back on the next call.
    tool_calls: list[ToolCall] = Field(default_factory=list)
    # Set on tool turns: which assistant tool call this result answers.
    tool_call_id: str | None = None
    name: str | None = None

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> Message:
        return cls(role="assistant", content=content)

    @classmethod
    def tool_result(cls, *, tool_call_id: str, name: str, content: str) -> Message:
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)


class ToolCall(BaseModel):
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolSpec(BaseModel):
    """A tool offered to the model.

    ``description`` is what the model actually reads when choosing a tool, so it
    is written in Turkish and explains when the tool should and should not be used.
    """

    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ChatResponse(BaseModel):
    """The model's answer to a chat request."""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: Usage = Field(default_factory=Usage)
    model: str = ""

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)

    def to_message(self) -> Message:
        return Message(role="assistant", content=self.content, tool_calls=self.tool_calls)


Message.model_rebuild()
