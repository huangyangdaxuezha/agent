"""Agent 主循环：think → act（工具）→ observe，直到模型不再调用工具或达到步数上限。

核心层不认识任何具体模型或工具，只依赖抽象接口，因此可被假模型完整单测。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ..config import Config
from ..memory.short_term import ConversationMemory
from ..tools.registry import ConfirmFn, ToolRegistry
from .prompt import DEFAULT_SYSTEM_PROMPT, build_messages
from .types import LLMResponse, Message

if TYPE_CHECKING:  # 仅为类型标注，运行时不产生依赖
    from ..llm.base import LLMClient


class AgentLoop:
    def __init__(
        self,
        llm: "LLMClient",
        memory: ConversationMemory | None = None,
        tools: ToolRegistry | None = None,
        config: Config | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        confirm: ConfirmFn | None = None,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config or Config()
        self.llm = llm
        self.memory = memory or ConversationMemory(max_messages=self.config.max_history)
        self.tools = tools or ToolRegistry()
        self.system_prompt = system_prompt
        self.confirm = confirm
        self.logger = logger

    def _log(self, text: str) -> None:
        if self.logger:
            self.logger(text)

    def run(self, user_input: str) -> str:
        """执行一轮对话，返回助手最终回复文本。"""
        self.memory.add(Message(role="user", content=user_input))

        for step in range(1, self.config.max_steps + 1):
            messages = build_messages(self.system_prompt, self.memory.messages)
            self._log(f"step {step}: 请求模型，消息数 {len(messages)}")

            try:
                response = self.llm.chat(messages, self.tools.specs())
            except Exception as exc:  # 模型异常转化为可读文本，不让 CLI 崩溃
                self._log(f"step {step}: 模型调用失败 {exc}")
                return f"[模型调用失败] {exc}"

            if not response.has_tool_calls:
                self.memory.add(Message(role="assistant", content=response.content))
                return response.content

            self.memory.add(Message(role="assistant", content=response.content))
            self._run_tools(step, response)

        notice = f"[已达到最大步数 {self.config.max_steps}，提前结束本轮]"
        self._log(notice)
        return notice

    def _run_tools(self, step: int, response: LLMResponse) -> None:
        for call in response.tool_calls:
            result = self.tools.execute(call, confirm=self.confirm)
            self._log(f"step {step}: 工具 {result.name} -> {'错误' if result.is_error else '成功'}")
            self.memory.add(
                Message(
                    role="tool",
                    content=result.content,
                    name=result.name,
                    tool_call_id=result.call_id,
                )
            )
