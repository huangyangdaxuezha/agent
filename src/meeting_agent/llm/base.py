"""模型层抽象接口。core 只依赖这里的抽象，方便替换供应商或注入假模型做测试。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..core.types import LLMResponse, Message
from ..tools.registry import ToolSpec


class LLMError(RuntimeError):
    """模型调用失败（网络、鉴权、返回格式异常等）。"""


class LLMClient(ABC):
    @abstractmethod
    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> LLMResponse:
        """发起一次对话，返回统一结构的响应。"""
        raise NotImplementedError
