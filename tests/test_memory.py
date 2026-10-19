from meeting_agent.core.types import Message
from meeting_agent.memory.short_term import ConversationMemory
from meeting_agent.memory.store import JsonSessionStore, SessionStoreError


def test_add_keeps_order():
    memory = ConversationMemory(max_messages=10)
    memory.add_user("问题")
    memory.add_assistant("回答")
    assert [m.role for m in memory.messages] == ["user", "assistant"]


def test_trim_to_max_messages():
    memory = ConversationMemory(max_messages=3)
    for i in range(10):
        memory.add_user(f"消息{i}")
    assert len(memory.messages) == 3
    assert memory.messages[-1].content == "消息9"


def test_trim_drops_orphan_tool_message():
    memory = ConversationMemory(max_messages=3)
    memory.add_user("问题")
    memory.add_tool("工具结果", name="demo")  # 会被裁剪
    memory.add_assistant("回答")
    memory.add_tool("工具结果2", name="demo")
    memory.add_user("再问")
    assert memory.messages[0].role != "tool"


def test_clear():
    memory = ConversationMemory()
    memory.add_user("x")
    memory.clear()
    assert memory.messages == ()


def test_invalid_max_messages():
    try:
        ConversationMemory(max_messages=0)
    except ValueError:
        pass
    else:
        raise AssertionError("max_messages 应校验")


def test_store_round_trip(tmp_path):
    store = JsonSessionStore(tmp_path / "sessions" / "s1.json")
    store.save([Message(role="user", content="你好"), Message(role="assistant", content="hi")])

    assert store.exists()
    loaded = store.load()
    assert [m.content for m in loaded] == ["你好", "hi"]
    assert loaded[0].role == "user"


def test_store_load_missing_file_returns_empty(tmp_path):
    assert JsonSessionStore(tmp_path / "nope.json").load() == []


def test_store_invalid_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    try:
        JsonSessionStore(path).load()
    except SessionStoreError:
        pass
    else:
        raise AssertionError("坏 JSON 应抛 SessionStoreError")
