"""Agent 核心层：与具体模型、工具实现无关。

注意：这里**不在导入时**加载 loop。AgentLoop 依赖 memory，而 memory 又依赖 core.types，
若在包初始化阶段就把 loop 拉进来，先导入 memory.* 的场景会触发循环导入。
AgentLoop 通过模块级 __getattr__ 延迟提供，用法保持不变。
"""

from .prompt import DEFAULT_SYSTEM_PROMPT, build_messages
from .types import LLMResponse, Message, ToolCall, ToolResult

__all__ = [
    "AgentLoop",
    "DEFAULT_SYSTEM_PROMPT",
    "build_messages",
    "LLMResponse",
    "Message",
    "ToolCall",
    "ToolResult",
]


def __getattr__(name: str):
    if name == "AgentLoop":
        from .loop import AgentLoop

        return AgentLoop
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
