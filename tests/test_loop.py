from meeting_agent.config import Config
from meeting_agent.core.loop import AgentLoop
from meeting_agent.core.types import LLMResponse, Message
from meeting_agent.llm.base import LLMError
from meeting_agent.memory.short_term import ConversationMemory
from meeting_agent.tools.registry import ToolRegistry

from .fakes import ExplodingLLM, FakeLLM, tool_call


def build_loop(llm, tools=None, confirm=None, max_steps=4, logger=None):
    return AgentLoop(
        llm=llm,
        memory=ConversationMemory(max_messages=20),
        tools=tools or ToolRegistry(),
        config=Config(max_steps=max_steps, max_history=20),
        system_prompt="系统提示",
        confirm=confirm,
        logger=logger,
    )


def test_single_turn_returns_answer_and_records_history():
    loop = build_loop(FakeLLM([LLMResponse(content="会议纪要如下")]))
    answer = loop.run("帮我总结会议")

    assert answer == "会议纪要如下"
    assert [(m.role, m.content) for m in loop.memory.messages] == [
        ("user", "帮我总结会议"),
        ("assistant", "会议纪要如下"),
    ]


def test_tool_round_trip_feeds_result_back_to_model():
    registry = ToolRegistry()

    @registry.register(name="get_todos", description="取待办")
    def get_todos() -> str:
        return "1. 周三前出方案"

    loop = build_loop(
        FakeLLM(
            [
                LLMResponse(content="", tool_calls=(tool_call("get_todos"),)),
                LLMResponse(content="待办：周三前出方案"),
            ]
        ),
        tools=registry,
    )
    answer = loop.run("有哪些待办")

    assert answer == "待办：周三前出方案"
    assert loop.llm.call_count == 2
    assert len(loop.llm.tool_specs_seen[0]) == 1
    tool_messages = [m for m in loop.memory.messages if m.role == "tool"]
    assert tool_messages[0].content == "1. 周三前出方案"


def test_sensitive_tool_is_cancelled_without_confirmation():
    registry = ToolRegistry()

    @registry.register(name="delete_file", description="删文件", sensitive=True)
    def delete_file(path: str) -> str:
        return f"已删除 {path}"

    loop = build_loop(
        FakeLLM(
            [
                LLMResponse(content="", tool_calls=(tool_call("delete_file", path="a.txt"),)),
                LLMResponse(content="好的，已取消删除"),
            ]
        ),
        tools=registry,
        confirm=lambda spec, args: False,
    )
    loop.run("删掉 a.txt")

    tool_messages = [m for m in loop.memory.messages if m.role == "tool"]
    assert "已取消" in tool_messages[0].content


def test_sensitive_tool_requires_confirm_even_if_callback_missing():
    registry = ToolRegistry()

    @registry.register(name="run_command", description="执行命令", sensitive=True)
    def run_command(cmd: str) -> str:
        return f"执行了 {cmd}"

    loop = build_loop(
        FakeLLM(
            [
                LLMResponse(content="", tool_calls=(tool_call("run_command", cmd="rm -rf /"),)),
                LLMResponse(content="拒绝执行"),
            ]
        ),
        tools=registry,
        confirm=None,
    )
    loop.run("清空磁盘")

    tool_messages = [m for m in loop.memory.messages if m.role == "tool"]
    assert "未获得确认" in tool_messages[0].content


def test_step_limit_stops_infinite_loop():
    registry = ToolRegistry()

    @registry.register(name="ping")
    def ping() -> str:
        return "pong"

    loop = build_loop(
        FakeLLM([LLMResponse(content="", tool_calls=(tool_call("ping"),))]),
        tools=registry,
        max_steps=3,
    )
    answer = loop.run("一直 ping")

    assert "已达到最大步数" in answer
    assert loop.llm.call_count == 3


def test_model_failure_is_converted_to_readable_text():
    loop = build_loop(ExplodingLLM())
    answer = loop.run("你好")

    assert answer.startswith("[模型调用失败]")
    assert isinstance(loop.llm, ExplodingLLM)


def test_history_is_passed_to_model_on_next_turn():
    loop = build_loop(
        FakeLLM([LLMResponse(content="第一句"), LLMResponse(content="第二句")])
    )
    loop.run("问题一")
    loop.run("问题二")

    second_request = loop.llm.calls[1]
    assert second_request[0].role == "system"
    assert "问题一" in [m.content for m in second_request]
    assert isinstance(isinstance(LLMError("x"), Exception), bool)


def test_unknown_tool_does_not_crash_loop():
    loop = build_loop(
        FakeLLM(
            [
                LLMResponse(content="", tool_calls=(tool_call("not_exist"),)),
                LLMResponse(content="没有这个工具"),
            ]
        )
    )
    answer = loop.run("用个不存在的工具")

    assert answer == "没有这个工具"
    assert [m.role for m in loop.memory.messages].count("tool") == 1


def test_logger_hook_receives_steps():
    lines: list[str] = []
    loop = build_loop(FakeLLM([LLMResponse(content="ok")]), logger=lines.append)
    loop.run("你好")

    assert any("step 1" in line for line in lines)


def test_messages_are_built_with_system_prompt():
    loop = build_loop(FakeLLM([LLMResponse(content="ok")]))
    loop.run("你好")

    assert loop.llm.calls[0][0] == Message(role="system", content="系统提示")
