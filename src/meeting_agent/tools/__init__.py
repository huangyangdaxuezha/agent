"""能力层：Agent 能做的事。v1 未内置任何执行类工具，仅保留注册机制。"""

from .registry import (
    EMPTY_PARAMETERS,
    ConfirmFn,
    ToolRegistry,
    ToolSpec,
    UnknownToolError,
    describe_tools,
)

__all__ = [
    "EMPTY_PARAMETERS",
    "ConfirmFn",
    "ToolRegistry",
    "ToolSpec",
    "UnknownToolError",
    "describe_tools",
]
