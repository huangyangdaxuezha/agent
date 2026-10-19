from meeting_agent.core.prompt import DEFAULT_SYSTEM_PROMPT, build_messages
from meeting_agent.core.types import Message


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
