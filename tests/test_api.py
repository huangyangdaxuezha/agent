import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from meeting_agent.api import create_app, deny_sensitive  # noqa: E402
from meeting_agent.config import Config  # noqa: E402
from meeting_agent.core.types import LLMResponse  # noqa: E402
from meeting_agent.memory.repository import SQLiteRepository  # noqa: E402
from meeting_agent.tools.registry import ToolRegistry  # noqa: E402

from .fakes import FakeLLM, tool_call  # noqa: E402


def build_client(tmp_path, llm=None, tools=None):
    app = create_app(
        config=Config(provider="echo", api_key="secret-should-not-leak"),
        llm=llm or FakeLLM([LLMResponse(content="会议纪要如下")]),
        tools=tools or ToolRegistry(),
        session_dir=tmp_path / "sessions",
        repository=SQLiteRepository(tmp_path / "db.sqlite"),
    )
    return TestClient(app)


def test_index_page_is_served(tmp_path):
    response = build_client(tmp_path).get("/")
    assert response.status_code == 200
    assert "会议小助手" in response.text


def test_chat_returns_reply_and_session(tmp_path):
    response = build_client(tmp_path).post("/api/chat", json={"message": "总结会议"})

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "会议纪要如下"
    assert data["session_id"]


def test_chat_persists_history_for_session(tmp_path):
    client = build_client(tmp_path)
    first = client.post("/api/chat", json={"message": "第一句"}).json()

    second = client.post(
        "/api/chat", json={"message": "第二句", "session_id": first["session_id"]}
    )
    assert second.status_code == 200

    history = client.get(f"/api/sessions/{first['session_id']}").json()["messages"]
    assert [m["content"] for m in history] == ["第一句", "会议纪要如下", "第二句", "会议纪要如下"]


def test_sessions_are_isolated(tmp_path):
    client = build_client(tmp_path)
    a = client.post("/api/chat", json={"message": "A 的会议"}).json()["session_id"]
    b = client.post("/api/chat", json={"message": "B 的会议"}).json()["session_id"]

    history_a = client.get(f"/api/sessions/{a}").json()["messages"]
    history_b = client.get(f"/api/sessions/{b}").json()["messages"]

    assert len(history_a) == 2 and len(history_b) == 2
    assert "B 的会议" not in [m["content"] for m in history_a]
    assert "A 的会议" not in [m["content"] for m in history_b]


def test_invalid_session_id_is_rejected(tmp_path):
    client = build_client(tmp_path)
    assert client.post("/api/chat", json={"message": "x", "session_id": "../evil"}).status_code == 400
    assert client.get("/api/sessions/..%2Fevil").status_code in {400, 404}


def test_empty_message_is_rejected(tmp_path):
    assert build_client(tmp_path).post("/api/chat", json={"message": ""}).status_code == 422


def test_clear_session(tmp_path):
    client = build_client(tmp_path)
    session_id = client.post("/api/chat", json={"message": "你好"}).json()["session_id"]

    assert client.delete(f"/api/sessions/{session_id}").json()["cleared"] is True
    assert client.get(f"/api/sessions/{session_id}").json()["messages"] == []


def test_info_never_exposes_api_key(tmp_path):
    data = build_client(tmp_path).get("/api/info").json()

    assert "api_key" not in data
    assert "secret-should-not-leak" not in str(data)
    assert data["provider"] == "echo"
    assert data["max_steps"] == 5


def test_sensitive_tool_is_denied_on_web(tmp_path):
    executed = []
    registry = ToolRegistry()

    @registry.register(name="delete_file", sensitive=True)
    def delete_file(path: str) -> str:
        executed.append(path)
        return f"已删除 {path}"

    client = build_client(
        tmp_path,
        llm=FakeLLM(
            [
                LLMResponse(content="", tool_calls=(tool_call("delete_file", path="a.txt"),)),
                LLMResponse(content="好的，已取消删除"),
            ]
        ),
        tools=registry,
    )
    data = client.post("/api/chat", json={"message": "删掉 a.txt"}).json()

    assert executed == []
    assert data["reply"] == "好的，已取消删除"
    history = client.get(f"/api/sessions/{data['session_id']}").json()["messages"]
    assert any("已取消" in m["content"] for m in history if m["role"] == "tool")


def test_deny_sensitive_returns_false():
    from meeting_agent.tools.registry import ToolSpec

    assert deny_sensitive(ToolSpec(name="x", sensitive=True), {}) is False


def test_main_reuses_running_service_instead_of_crashing(monkeypatch):
    """端口已被本服务占用时，应提示直接用，而不是抛一堆 traceback。"""
    import uvicorn

    from meeting_agent import api as api_module

    def boom(*args, **kwargs):
        raise OSError("[Errno 10048] error while attempting to bind on address")

    monkeypatch.setattr(uvicorn, "run", boom)
    monkeypatch.setattr(api_module, "create_app", lambda **kwargs: object())
    monkeypatch.setattr(api_module, "load_dotenv", lambda: None)
    monkeypatch.setattr(api_module, "port_already_serving", lambda host, port: True)

    assert api_module.main(["--port", "8123"]) == 0


def test_main_exits_when_port_taken_by_other_program(monkeypatch):
    import uvicorn

    from meeting_agent import api as api_module

    def boom(*args, **kwargs):
        raise OSError("bind failed")

    monkeypatch.setattr(uvicorn, "run", boom)
    monkeypatch.setattr(api_module, "create_app", lambda **kwargs: object())
    monkeypatch.setattr(api_module, "load_dotenv", lambda: None)
    monkeypatch.setattr(api_module, "port_already_serving", lambda host, port: False)

    with pytest.raises(SystemExit):
        api_module.main(["--port", "8123"])
