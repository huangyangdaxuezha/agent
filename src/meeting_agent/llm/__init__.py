"""模型层：抽象接口 + 具体实现（可替换供应商）。"""

from .base import LLMClient, LLMError
from .echo import EchoLLM
from .http import OpenAICompatibleClient

__all__ = ["LLMClient", "LLMError", "EchoLLM", "OpenAICompatibleClient"]
