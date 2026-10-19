from meeting_agent.core.types import (
    LLMResponse,
    Message,
    ToolCall,
    ToolResult,
    parse_tool_arguments,
)


def test_message_to_dict_omits_empty_fields():
    assert Message(role="user", content="hi").to_dict() == {"role": "user", "content": "hi"}


def test_message_to_dict_keeps_tool_metadata():
    data = Message(role="tool", content="out", name="demo", tool_call_id="c1").to_dict()
    assert data["name"] == "demo"
    assert data["tool_call_id"] == "c1"


def test_llm_response_detects_tool_calls():
    assert not LLMResponse(content="ok").has_tool_calls
    assert LLMResponse(tool_calls=(ToolCall(id="1", name="demo"),)).has_tool_calls


def test_parse_tool_arguments_handles_bad_input():
    assert parse_tool_arguments('{"a": 1}') == {"a": 1}
    assert parse_tool_arguments({"a": 1}) == {"a": 1}
    assert parse_tool_arguments("not json") == {}
    assert parse_tool_arguments(None) == {}


def test_tool_result_error_flag():
    result = ToolResult(call_id="1", name="demo", content="失败", is_error=True)
    assert result.is_error
