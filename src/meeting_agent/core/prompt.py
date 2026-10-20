"""提示词模板与上下文拼装。

提示词迭代最频繁，单独隔离后，改文案不需要触碰任何逻辑代码。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

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
    "待办与纪要分开存储：纪要里不含待办列表，查待办请用 list_todos。"
    "用户问会议列表时只列会议（id、标题、日期），不要附带待办内容；"
    "用户问待办时只列待办（内容、负责人、截止时间、来源会议），不要重复列会议。"
    "回答必须基于工具返回的内容，查不到就直说查不到，不要编造。"
)


def sanitize_messages(messages: Sequence[Message]) -> list[Message]:
    """清洗历史，保证符合 OpenAI 协议：tool 消息必须紧跟带 tool_calls 的 assistant。

    - 没有前置 assistant.tool_calls 的 tool 消息（孤儿）直接丢弃；
    - assistant 的 tool_calls 若没有对应 tool 响应，则去掉（无正文时整条丢弃）；
    - 内容为空的 assistant 消息丢弃。

    这样旧会话文件（当时还没保存 tool_calls）也不会再触发 400。
    """
    responded = {
        message.tool_call_id
        for message in messages
        if message.role == "tool" and message.tool_call_id
    }
    cleaned: list[Message] = []
    declared: set[str] = set()
    for message in messages:
        if message.role == "assistant":
            calls = tuple(call for call in message.tool_calls if call.id in responded)
            if not calls and not message.content.strip():
                declared = set()
                continue
            cleaned.append(replace(message, tool_calls=calls))
            declared = {call.id for call in calls}
        elif message.role == "tool":
            if message.tool_call_id and message.tool_call_id in declared:
                cleaned.append(message)
                declared.discard(message.tool_call_id)
        else:
            cleaned.append(message)
            declared = set()
    return cleaned


def build_messages(
    system_prompt: str,
    history: Sequence[Message],
    user_input: str | None = None,
) -> list[Message]:
    """拼装一次请求所需的消息：系统提示 + 清洗后的历史 + 本轮用户输入。"""
    messages: list[Message] = [Message(role="system", content=system_prompt)]
    messages.extend(sanitize_messages(history))
    if user_input:
        messages.append(Message(role="user", content=user_input))
    return messages
