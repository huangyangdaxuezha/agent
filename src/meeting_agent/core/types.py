"""全局数据契约：消息、工具调用、工具结果、模型响应。

这一层不依赖任何具体模型或工具实现，是 core / llm / tools / memory 之间的通用语言。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class Message:
    """一条对话消息。tool 角色时携带 name 与 tool_call_id。"""

    role: Role
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            data["name"] = self.name
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        return data


@dataclass(frozen=True)
class ToolCall:
    """模型发起的一次工具调用请求。"""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    """工具执行结果，会作为 tool 角色消息回灌给模型。"""

    call_id: str
    name: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class LLMResponse:
    """模型单次响应：文本 + 若干工具调用请求。"""

    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


def parse_tool_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """把模型给出的 arguments（JSON 字符串或字典）安全地解析为字典。"""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
