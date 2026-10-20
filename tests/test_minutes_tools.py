import json

from meeting_agent.config import Config
from meeting_agent.core.loop import AgentLoop
from meeting_agent.core.types import LLMResponse
from meeting_agent.memory.repository import SQLiteRepository
from meeting_agent.memory.short_term import ConversationMemory
from meeting_agent.tools.builtin import register_minutes_tools
from meeting_agent.tools.registry import ToolRegistry

from .fakes import FakeLLM, tool_call


def build(tmp_path):
    repository = SQLiteRepository(tmp_path / "db.sqlite")
    registry = register_minutes_tools(ToolRegistry(), repository)
    return repository, registry


def seed(repository, title="周会", date="2026-10-20"):
    meeting_id = repository.create_meeting(title=title, meeting_date=date)
    repository.save_minutes(meeting_id, content="## 结论\n下周一上线", summary="上线确定")
    return meeting_id


def test_list_meetings_tool(tmp_path):
    repository, registry = build(tmp_path)
    seed(repository, title="预算评审")

    result = json.loads(registry.execute(tool_call("list_meetings", keyword="预算")).content)

    assert result["count"] == 1
    assert result["meetings"][0]["title"] == "预算评审"


def test_get_meeting_minutes_tool(tmp_path):
    repository, registry = build(tmp_path)
    meeting_id = seed(repository)

    result = json.loads(
        registry.execute(tool_call("get_meeting_minutes", meeting_id=meeting_id)).content
    )

    assert result["id"] == meeting_id
    assert "下周一上线" in result["content"]


def test_update_meeting_tool_changes_only_requested_field(tmp_path):
    repository, registry = build(tmp_path)
    meeting_id = seed(repository)

    result = json.loads(
        registry.execute(tool_call("update_meeting", meeting_id=meeting_id, title="周会改名")).content
    )

    assert result["ok"] is True
    record = repository.get_meeting(meeting_id)
    assert record["title"] == "周会改名"
    assert record["meeting_date"] == "2026-10-20"
    assert repository.changes(meeting_id)[0]["field"] == "title"


def test_save_meeting_minutes_tool(tmp_path):
    repository, registry = build(tmp_path)

    result = json.loads(
        registry.execute(
            tool_call("save_meeting_minutes", title="临时会议", content="正文")
        ).content
    )

    assert result["ok"] is True
    assert repository.get_meeting(result["meeting_id"])["title"] == "临时会议"


def test_tools_are_not_sensitive_so_web_can_run_them(tmp_path):
    """需求：查纪要、改纪要都不弹确认，但必须是非敏感工具，否则 Web 端会被拒绝。"""
    _, registry = build(tmp_path)

    for spec in registry.specs():
        assert spec.sensitive is False, spec.name


def test_update_tool_runs_without_confirm_callback(tmp_path):
    repository, registry = build(tmp_path)
    meeting_id = seed(repository)

    result = registry.execute(
        tool_call("update_meeting", meeting_id=meeting_id, title="无确认也能改"),
        confirm=None,
    )

    assert result.is_error is False
    assert repository.get_meeting(meeting_id)["title"] == "无确认也能改"


def test_agent_updates_title_through_tool(tmp_path):
    """端到端：用户说改标题 → 模型调工具 → 数据库真的改了。"""
    repository, registry = build(tmp_path)
    meeting_id = seed(repository)

    loop = AgentLoop(
        llm=FakeLLM(
            [
                LLMResponse(
                    content="",
                    tool_calls=(tool_call("update_meeting", meeting_id=meeting_id, title="10月20日产品评审"),),
                ),
                LLMResponse(content="标题已改为「10月20日产品评审」"),
            ]
        ),
        memory=ConversationMemory(max_messages=20),
        tools=registry,
        config=Config(),
    )
    reply = loop.run("把 10 月 20 日那场会的标题改成 10月20日产品评审")

    assert reply == "标题已改为「10月20日产品评审」"
    assert repository.get_meeting(meeting_id)["title"] == "10月20日产品评审"
    assert repository.get_meeting(meeting_id)["meeting_date"] == "2026-10-20"


def test_unknown_meeting_id_returns_friendly_error(tmp_path):
    _, registry = build(tmp_path)

    result = registry.execute(tool_call("get_meeting_minutes", meeting_id=999))

    assert "未找到会议" in result.content
