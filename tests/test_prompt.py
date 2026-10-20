from meeting_agent.core.prompt import (
    DEFAULT_SYSTEM_PROMPT,
    build_messages,
    sanitize_messages,
)
from meeting_agent.core.types import Message, ToolCall


def _assistant_with_call(call_id: str = "c1") -> Message:
    return Message(
        role="assistant",
        content="",
        tool_calls=(ToolCall(id=call_id, name="update_meeting", arguments={}),),
    )


def test_sanitize_drops_orphan_tool_message():
    """旧会话文件里 tool 消息没有配套 assistant.tool_calls，必须丢弃，否则模型接口 400。"""
    history = [
        Message(role="user", content="改标题"),
        Message(role="tool", content="结果", name="update_meeting", tool_call_id="c1"),
    ]
    assert [m.role for m in sanitize_messages(history)] == ["user"]


def test_sanitize_keeps_valid_tool_pair():
    history = [
        Message(role="user", content="改标题"),
        _assistant_with_call("c1"),
        Message(role="tool", content="结果", name="update_meeting", tool_call_id="c1"),
        Message(role="assistant", content="已修改"),
    ]
    cleaned = sanitize_messages(history)
    assert [m.role for m in cleaned] == ["user", "assistant", "tool", "assistant"]
    assert cleaned[1].tool_calls[0].id == "c1"


def test_sanitize_strips_tool_calls_without_response():
    history = [
        Message(role="user", content="改标题"),
        Message(
            role="assistant",
            content="我准备调用工具",
            tool_calls=(ToolCall(id="c1", name="update_meeting", arguments={}),),
        ),
        Message(role="user", content="算了不用了"),
    ]
    cleaned = sanitize_messages(history)

    assert cleaned[1].role == "assistant"
    assert cleaned[1].content == "我准备调用工具"
    assert cleaned[1].tool_calls == ()


def test_sanitize_drops_empty_assistant_with_unanswered_calls():
    history = [Message(role="user", content="改标题"), _assistant_with_call("c9")]
    assert [m.role for m in sanitize_messages(history)] == ["user"]


def test_sanitize_drops_empty_assistant_without_calls():
    history = [Message(role="user", content="x"), Message(role="assistant", content="   ")]
    assert [m.role for m in sanitize_messages(history)] == ["user"]


def test_build_messages_order():
    history = [Message(role="user", content="上一条"), Message(role="assistant", content="回复")]
    messages = build_messages("系统提示", history, "本轮问题")

    assert messages[0].role == "system"
    assert messages[0].content == "系统提示"
    assert [m.role for m in messages[1:]] == ["user", "assistant", "user"]
    assert messages[-1].content == "本轮问题"


def test_build_messages_without_user_input():
    messages = build_messages("系统提示", [Message(role="user", content="x")])
    assert len(messages) == 2


def test_default_prompt_mentions_meeting_tasks():
    assert "会议" in DEFAULT_SYSTEM_PROMPT
    assert "待办" in DEFAULT_SYSTEM_PROMPT
