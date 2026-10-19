"""会话持久化：把历史消息存成 JSON，便于下次继续或人工检查。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from ..core.types import Message


class SessionStoreError(RuntimeError):
    """会话文件读取失败（格式错误等）。"""


class JsonSessionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.exists()

    def save(self, messages: Sequence[Message]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [m.to_dict() for m in messages]
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self) -> list[Message]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise SessionStoreError(f"会话文件解析失败: {self.path}") from exc
        if not isinstance(raw, list):
            raise SessionStoreError("会话文件格式错误：顶层应为数组")
        return [
            Message(
                role=item.get("role", "user"),
                content=str(item.get("content", "")),
                name=item.get("name"),
                tool_call_id=item.get("tool_call_id"),
            )
            for item in raw
            if isinstance(item, dict)
        ]
