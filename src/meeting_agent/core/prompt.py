"""提示词模板与上下文拼装。

提示词迭代最频繁，单独隔离后，改文案不需要触碰任何逻辑代码。
"""

from __future__ import annotations

from collections.abc import Sequence

from .types import Message

DEFAULT_SYSTEM_PROMPT = (
    "你是「会议小助手」，专注于会议相关任务：\n"
    "1. 根据提供的会议记录或讨论内容回答问题；\n"
    "2. 提炼会议纪要与结论；\n"
    "3. 抽取待办事项（尽量给出负责人与截止时间，缺失时说明缺失）；\n"
    "回答要求：简洁、结构化、只基于已知信息，不编造未提及的内容；"
    "信息不足时直接说明需要补充什么。"
)


TOOL_USAGE_HINT = (
    "\n你可以使用会议纪要工具：先用 list_meetings 或 get_meeting_minutes 查到具体会议，"
    "再用 update_meeting 只修改用户要求改的字段（未提供的字段保持原值）。"
    "回答必须基于工具返回的内容，查不到就直说查不到，不要编造。"
)


def build_messages(
    system_prompt: str,
    history: Sequence[Message],
    user_input: str | None = None,
) -> list[Message]:
    """拼装一次请求所需的消息：系统提示 + 历史 + 本轮用户输入（可选）。"""
    messages: list[Message] = [Message(role="system", content=system_prompt)]
    messages.extend(history)
    if user_input:
        messages.append(Message(role="user", content=user_input))
    return messages
