from meeting_agent.tools.registry import (
    EMPTY_PARAMETERS,
    ToolRegistry,
    ToolSpec,
    UnknownToolError,
    describe_tools,
)

from .fakes import tool_call


def test_register_decorator_collects_spec():
    registry = ToolRegistry()

    @registry.register(name="summarize", description="总结会议", parameters={"type": "object"})
    def summarize() -> str:
        return "纪要"

    assert [s.name for s in registry.specs()] == ["summarize"]
    assert registry.get("summarize").description == "总结会议"
    assert registry.get("summarize").parameters == {"type": "object"}
    assert summarize() == "纪要"


def test_register_defaults_to_function_name_and_docstring():
    registry = ToolRegistry()

    @registry.register()
    def echo_tool() -> str:
        """回显工具"""
        return "x"

    spec = registry.get("echo_tool")
    assert spec.description == "回显工具"
    assert spec.parameters == EMPTY_PARAMETERS
    assert spec.sensitive is False


def test_execute_returns_handler_output():
    registry = ToolRegistry()

    @registry.register(name="get_todos")
    def get_todos(owner: str = "") -> str:
        return f"待办负责人={owner}"

    result = registry.execute(tool_call("get_todos", owner="张三"))
    assert result.content == "待办负责人=张三"
    assert result.is_error is False


def test_execute_unknown_tool():
    result = ToolRegistry().execute(tool_call("missing"))
    assert result.is_error
    assert "未注册" in result.content


def test_execute_captures_handler_exception():
    registry = ToolRegistry()

    @registry.register(name="boom")
    def boom() -> str:
        raise RuntimeError("炸了")

    result = registry.execute(tool_call("boom"))
    assert result.is_error
    assert "工具执行失败" in result.content


def test_sensitive_tool_requires_confirmation():
    registry = ToolRegistry()

    @registry.register(name="delete_file", sensitive=True)
    def delete_file(path: str) -> str:
        return f"删除 {path}"

    denied = registry.execute(tool_call("delete_file", path="a.txt"), confirm=lambda s, a: False)
    assert denied.is_error and "已取消" in denied.content

    approved = registry.execute(tool_call("delete_file", path="a.txt"), confirm=lambda s, a: True)
    assert approved.content == "删除 a.txt"


def test_sensitive_tool_without_confirm_callback_is_blocked():
    registry = ToolRegistry()
    registry.add(ToolSpec(name="run_command", sensitive=True, handler=lambda: "done"))

    result = registry.execute(tool_call("run_command"))
    assert result.is_error and "未获得确认" in result.content


def test_non_sensitive_tool_ignores_confirm():
    registry = ToolRegistry()
    registry.add(ToolSpec(name="safe", handler=lambda: "ok"))

    result = registry.execute(tool_call("safe"), confirm=None)
    assert result.content == "ok"


def test_get_unknown_raises():
    try:
        ToolRegistry().get("nope")
    except UnknownToolError:
        pass
    else:
        raise AssertionError("应抛出 UnknownToolError")


def test_add_requires_name():
    registry = ToolRegistry()
    try:
        registry.add(ToolSpec(name=""))
    except ValueError:
        pass
    else:
        raise AssertionError("空工具名应被拒绝")


def test_describe_tools_for_logging():
    registry = ToolRegistry()
    registry.add(ToolSpec(name="a", description="安全工具"))
    registry.add(ToolSpec(name="b", description="危险工具", sensitive=True))

    text = describe_tools(registry.specs())
    assert "a: 安全工具" in text
    assert "b[敏感]: 危险工具" in text
    assert describe_tools(()) == "（无可用工具）"
