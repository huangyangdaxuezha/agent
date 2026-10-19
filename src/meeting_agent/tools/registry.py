"""工具注册表：加一个工具 = 注册一个函数，核心循环零改动。

敏感工具（sensitive=True）执行前必须经过确认回调，未获确认直接取消并回灌错误，
避免 Agent 擅自执行有副作用的操作。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..core.types import ToolCall, ToolResult

EMPTY_PARAMETERS: dict[str, object] = {"type": "object", "properties": {}, "required": []}

# 确认回调：接收工具定义与参数，返回是否放行
ConfirmFn = Callable[["ToolSpec", dict], bool]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str = ""
    parameters: dict[str, object] = field(default_factory=lambda: dict(EMPTY_PARAMETERS))
    sensitive: bool = False
    handler: Callable[..., str] | None = None


class UnknownToolError(KeyError):
    """请求了未注册的工具。"""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str | None = None,
        description: str = "",
        parameters: dict[str, object] | None = None,
        sensitive: bool = False,
    ) -> Callable[[Callable[..., str]], Callable[..., str]]:
        """装饰器形式注册工具。"""

        def decorator(func: Callable[..., str]) -> Callable[..., str]:
            self.add(
                ToolSpec(
                    name=name or func.__name__,
                    description=description or (func.__doc__ or "").strip(),
                    parameters=dict(parameters or EMPTY_PARAMETERS),
                    sensitive=sensitive,
                    handler=func,
                )
            )
            return func

        return decorator

    def add(self, spec: ToolSpec) -> None:
        if not spec.name:
            raise ValueError("工具名不能为空")
        self._tools[spec.name] = spec

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools.values())

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise UnknownToolError(f"未知工具: {name}") from exc

    def execute(self, call: ToolCall, confirm: ConfirmFn | None = None) -> ToolResult:
        try:
            spec = self.get(call.name)
        except UnknownToolError:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                content=f"工具 {call.name} 未注册",
                is_error=True,
            )

        arguments = dict(call.arguments)
        if spec.sensitive:
            approved = bool(confirm(spec, arguments)) if confirm else False
            if not approved:
                return ToolResult(
                    call_id=call.id,
                    name=spec.name,
                    content=f"已取消：敏感工具 {spec.name} 未获得确认",
                    is_error=True,
                )

        if spec.handler is None:
            return ToolResult(
                call_id=call.id, name=spec.name, content="工具未实现", is_error=True
            )

        try:
            output = spec.handler(**arguments)
        except Exception as exc:  # 工具异常不能打挂整个循环
            return ToolResult(
                call_id=call.id,
                name=spec.name,
                content=f"工具执行失败: {exc}",
                is_error=True,
            )
        return ToolResult(call_id=call.id, name=spec.name, content=str(output))


def describe_tools(tools: Sequence[ToolSpec]) -> str:
    """给日志/调试用的工具清单文本。"""
    if not tools:
        return "（无可用工具）"
    return "\n".join(f"- {t.name}{'[敏感]' if t.sensitive else ''}: {t.description}" for t in tools)
