"""离线占位模型：未配置真实模型时也能跑通整条链路（CLI / 循环 / 记忆 / 测试）。

发号施令不上网、不花钱，适合作为 v1 默认 provider。
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.types import LLMResponse, Message
from ..tools.registry import ToolSpec
from .base import LLMClient


class EchoLLM(LLMClient):
    def __init__(self, model: str = "", notice: str | None = None) -> None:
        self.model = model
        self.notice = notice or "[离线占位模型] 尚未配置真实模型，下面是回显结果。"

    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> LLMResponse:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        content = f"{self.notice}\n你刚才说：{last_user or '（空）'}"
        return LLMResponse(content=content)
