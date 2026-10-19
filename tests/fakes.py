"""测试用假模型：不发网络请求、不花钱，行为完全可控。"""

from __future__ import annotations

from collections.abc import Sequence

from meeting_agent.core.types import LLMResponse, Message, ToolCall
from meeting_agent.llm.base import LLMClient, LLMError
from meeting_agent.tools.registry import ToolSpec


class FakeLLM(LLMClient):
    """按预设脚本依次返回响应；脚本用尽后重复最后一项。"""

    def __init__(self, responses: Sequence[LLMResponse] | None = None) -> None:
        self.responses = list(responses or [LLMResponse(content="默认回复")])
        self.calls: list[list[Message]] = []
        self.tool_specs_seen: list[tuple[ToolSpec, ...]] = []

    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> LLMResponse:
        self.calls.append(list(messages))
        self.tool_specs_seen.append(tuple(tools))
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]

    @property
    def call_count(self) -> int:
        return len(self.calls)


class ExplodingLLM(LLMClient):
    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> LLMResponse:
        raise LLMError("假模型爆炸")


def tool_call(name: str = "demo", call_id: str = "call_1", **arguments: object) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=dict(arguments))
