"""OpenAI 兼容接口实现（仅用标准库 urllib，零第三方依赖）。

适用于 OpenAI 官方及绝大多数兼容 /v1/chat/completions 的供应商。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence

from ..core.types import LLMResponse, Message, ToolCall, parse_tool_arguments
from ..tools.registry import ToolSpec
from .base import LLMClient, LLMError


class OpenAICompatibleClient(LLMClient):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.3,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> LLMResponse:
        if not self.base_url or not self.model:
            raise LLMError("缺少 base_url 或 model，无法调用真实模型")

        payload: dict[str, object] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = [self._tool_payload(spec) for spec in tools]

        raw = self._post(payload)
        return self._parse(raw)

    @staticmethod
    def _tool_payload(spec: ToolSpec) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }

    def _post(self, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # 4xx / 5xx
            detail = exc.read().decode("utf-8", "ignore")
            raise LLMError(f"模型服务返回 {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMError(f"模型服务不可达: {exc}") from exc

        try:
            data = json.loads(text)
        except ValueError as exc:
            raise LLMError(f"模型返回非 JSON 内容: {text[:200]}") from exc
        if not isinstance(data, dict):
            raise LLMError("模型返回格式异常：顶层不是对象")
        return data

    @staticmethod
    def _parse(data: dict[str, object]) -> LLMResponse:
        try:
            message = data["choices"][0]["message"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"模型返回缺少 choices[0].message: {data}") from exc

        content = str(message.get("content") or "")
        calls = [
            ToolCall(
                id=str(call.get("id") or ""),
                name=str(call.get("function", {}).get("name") or ""),
                arguments=parse_tool_arguments(call.get("function", {}).get("arguments")),
            )
            for call in message.get("tool_calls") or []
        ]
        return LLMResponse(content=content, tool_calls=tuple(calls))
