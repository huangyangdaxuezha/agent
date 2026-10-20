"""内置工具：v1 只有会议纪要的查询与修改工具（minutes）。"""

from .minutes import register_minutes_tools

__all__ = ["register_minutes_tools"]
