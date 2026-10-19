"""会话内短期记忆：保存消息历史并按上限裁剪，防止上下文无限膨胀。"""

from __future__ import annotations

from ..core.types import Message


class ConversationMemory:
    def __init__(self, max_messages: int = 40) -> None:
        if max_messages < 1:
            raise ValueError("max_messages 必须 >= 1")
        self.max_messages = max_messages
        self._messages: list[Message] = []

    def add(self, message: Message) -> None:
        self._messages.append(message)
        self._trim()

    def add_user(self, content: str) -> None:
        self.add(Message(role="user", content=content))

    def add_assistant(self, content: str) -> None:
        self.add(Message(role="assistant", content=content))

    def add_tool(self, content: str, name: str, call_id: str = "") -> None:
        self.add(Message(role="tool", content=content, name=name, tool_call_id=call_id))

    @property
    def messages(self) -> tuple[Message, ...]:
        return tuple(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def _trim(self) -> None:
        if len(self._messages) <= self.max_messages:
            return
        self._messages = self._messages[-self.max_messages :]
        # 避免裁剪后首条是孤儿 tool 消息（缺少对应的 assistant 调用）
        while len(self._messages) > 1 and self._messages[0].role == "tool":
            self._messages.pop(0)
