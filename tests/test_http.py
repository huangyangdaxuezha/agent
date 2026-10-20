import io
import json
import urllib.error

import meeting_agent.llm.http as http_module
from meeting_agent.core.types import Message
from meeting_agent.llm.base import LLMError
from meeting_agent.llm.http import OpenAICompatibleClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def install_fake_urlopen(monkeypatch, payload):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(payload)

    monkeypatch.setattr(http_module.urllib.request, "urlopen", fake_urlopen)
    return captured


def test_chat_parses_content_and_endpoint(monkeypatch):
    captured = install_fake_urlopen(
        monkeypatch, {"choices": [{"message": {"content": "会议纪要如下"}}]}
    )
    client = OpenAICompatibleClient("https://api.example.com/v1/", "sk-test", "gpt-x")

    response = client.chat([Message(role="user", content="总结")])

    assert response.content == "会议纪要如下"
    assert captured["request"].full_url == "https://api.example.com/v1/chat/completions"
    assert captured["request"].get_header("Authorization") == "Bearer sk-test"
    assert json.loads(captured["request"].data)["model"] == "gpt-x"


def test_chat_parses_tool_calls(monkeypatch):
    install_fake_urlopen(
        monkeypatch,
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {"name": "get_todos", "arguments": '{"owner":"张三"}'},
                            }
                        ],
                    }
                }
            ]
        },
    )
    client = OpenAICompatibleClient("https://api.example.com/v1", "sk-test", "gpt-x")

    response = client.chat([Message(role="user", content="待办")])

    assert response.has_tool_calls
    assert response.tool_calls[0].name == "get_todos"
    assert response.tool_calls[0].arguments == {"owner": "张三"}


def test_payload_keeps_tool_call_pairing(monkeypatch):
    from meeting_agent.core.types import ToolCall

    captured = install_fake_urlopen(monkeypatch, {"choices": [{"message": {"content": "ok"}}]})
    client = OpenAICompatibleClient("https://api.example.com/v1", "sk-test", "gpt-x")

    client.chat(
        [
            Message(
                role="assistant",
                content="",
                tool_calls=(ToolCall(id="c1", name="t", arguments={"a": 1}),),
            ),
            Message(role="tool", content="result", name="t", tool_call_id="c1"),
        ]
    )

    payload = json.loads(captured["request"].data)
    assert payload["messages"][0]["tool_calls"][0]["id"] == "c1"
    assert payload["messages"][0]["tool_calls"][0]["function"]["name"] == "t"
    assert payload["messages"][1]["role"] == "tool"
    assert payload["messages"][1]["tool_call_id"] == "c1"


def test_tools_are_serialized_into_payload(monkeypatch):
    from meeting_agent.tools.registry import ToolSpec

    captured = install_fake_urlopen(monkeypatch, {"choices": [{"message": {"content": "ok"}}]})
    client = OpenAICompatibleClient("https://api.example.com/v1", "sk-test", "gpt-x")

    client.chat(
        [Message(role="user", content="x")],
        tools=(ToolSpec(name="t", description="d"),),
    )

    payload = json.loads(captured["request"].data)
    assert payload["tools"][0]["function"]["name"] == "t"


def test_missing_config_raises_without_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("不应发起网络请求")

    monkeypatch.setattr(http_module.urllib.request, "urlopen", fail)
    client = OpenAICompatibleClient("", "sk-test", "")

    try:
        client.chat([Message(role="user", content="x")])
    except LLMError:
        pass
    else:
        raise AssertionError("缺少配置应抛 LLMError")


def test_http_error_is_wrapped(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            "https://api.example.com/v1/chat/completions",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b"bad key"),
        )

    monkeypatch.setattr(http_module.urllib.request, "urlopen", fake_urlopen)
    client = OpenAICompatibleClient("https://api.example.com/v1", "sk-bad", "gpt-x")

    try:
        client.chat([Message(role="user", content="x")])
    except LLMError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("HTTP 错误应抛 LLMError")


def test_network_error_is_wrapped(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(http_module.urllib.request, "urlopen", fake_urlopen)
    client = OpenAICompatibleClient("https://api.example.com/v1", "sk-test", "gpt-x")

    try:
        client.chat([Message(role="user", content="x")])
    except LLMError:
        pass
    else:
        raise AssertionError("网络错误应抛 LLMError")


def test_malformed_response_is_wrapped(monkeypatch):
    install_fake_urlopen(monkeypatch, {"unexpected": True})
    client = OpenAICompatibleClient("https://api.example.com/v1", "sk-test", "gpt-x")

    try:
        client.chat([Message(role="user", content="x")])
    except LLMError:
        pass
    else:
        raise AssertionError("返回格式异常应抛 LLMError")
