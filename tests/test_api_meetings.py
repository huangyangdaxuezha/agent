import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from meeting_agent.api import create_app  # noqa: E402
from meeting_agent.config import Config  # noqa: E402
from meeting_agent.core.types import LLMResponse  # noqa: E402
from meeting_agent.memory.repository import SQLiteRepository  # noqa: E402

from .fakes import FakeLLM  # noqa: E402

VALID_JSON = json.dumps(
    {"title": "产品周会", "summary": "确定上线时间", "content": "## 结论\n下周一上线"},
    ensure_ascii=False,
)


def build_client(tmp_path, llm):
    app = create_app(
        config=Config(provider="echo"),
        llm=llm,
        session_dir=tmp_path / "sessions",
        repository=SQLiteRepository(tmp_path / "db.sqlite"),
    )
    return TestClient(app)


def test_generate_saves_minutes(tmp_path):
    client = build_client(tmp_path, FakeLLM([LLMResponse(content=VALID_JSON)]))

    data = client.post(
        "/api/meetings/generate", json={"raw_text": "会议原文…", "meeting_date": "2026-10-20"}
    ).json()

    assert data["structured"] is True
    assert data["title"] == "产品周会"
    assert data["version"] == 1
    detail = client.get(f"/api/meetings/{data['id']}").json()
    assert "下周一上线" in detail["content"]


def test_generate_falls_back_without_losing_text(tmp_path):
    client = build_client(tmp_path, FakeLLM([LLMResponse(content="模型没按格式输出")]))

    data = client.post("/api/meetings/generate", json={"raw_text": "原始会议记录"}).json()

    assert data["structured"] is False
    assert data["note"]
    assert client.get(f"/api/meetings/{data['id']}").status_code == 200


def test_generate_rejects_empty_raw_text(tmp_path):
    client = build_client(tmp_path, FakeLLM([LLMResponse(content=VALID_JSON)]))
    assert client.post("/api/meetings/generate", json={"raw_text": ""}).status_code == 422


def test_list_and_search(tmp_path):
    client = build_client(tmp_path, FakeLLM([LLMResponse(content=VALID_JSON)]))
    client.post("/api/meetings/generate", json={"raw_text": "预算讨论"})
    client.post(
        "/api/meetings/generate",
        json={"raw_text": "技术讨论", "title": "技术复盘", "meeting_date": "2026-10-19"},
    )

    assert client.get("/api/meetings").json()["count"] == 2
    assert client.get("/api/meetings?keyword=技术复盘").json()["count"] == 1
    assert client.get("/api/meetings?meeting_date=2026-10-19").json()["count"] == 1


def test_patch_updates_title(tmp_path):
    client = build_client(tmp_path, FakeLLM([LLMResponse(content=VALID_JSON)]))
    meeting_id = client.post("/api/meetings/generate", json={"raw_text": "x"}).json()["id"]

    updated = client.patch(f"/api/meetings/{meeting_id}", json={"title": "改后的标题"}).json()

    assert updated["title"] == "改后的标题"
    changes = client.get(f"/api/meetings/{meeting_id}/changes").json()["changes"]
    assert changes[0]["field"] == "title"


def test_patch_unknown_meeting_returns_404(tmp_path):
    client = build_client(tmp_path, FakeLLM([LLMResponse(content=VALID_JSON)]))
    assert client.patch("/api/meetings/999", json={"title": "x"}).status_code == 404


def test_get_unknown_meeting_returns_404(tmp_path):
    client = build_client(tmp_path, FakeLLM([LLMResponse(content=VALID_JSON)]))
    assert client.get("/api/meetings/999").status_code == 404


def test_meeting_payload_hides_internal_columns(tmp_path):
    client = build_client(tmp_path, FakeLLM([LLMResponse(content=VALID_JSON)]))
    meeting_id = client.post("/api/meetings/generate", json={"raw_text": "x"}).json()["id"]

    data = client.get(f"/api/meetings/{meeting_id}").json()

    assert "minutes_id" not in data
    assert "is_current" not in data


WITH_TODOS_JSON = json.dumps(
    {
        "title": "产品周会",
        "summary": "确定上线时间",
        "content": "## 结论\n下周一上线",
        "todos": [{"content": "准备上线材料", "owner": "张三", "due_date": "2026-10-25"}],
    },
    ensure_ascii=False,
)


def test_meeting_detail_does_not_include_todos(tmp_path):
    """需求：查会议纪要时不要看到待办数据。"""
    client = build_client(tmp_path, FakeLLM([LLMResponse(content=WITH_TODOS_JSON)]))
    meeting_id = client.post("/api/meetings/generate", json={"raw_text": "x"}).json()["id"]

    detail = client.get(f"/api/meetings/{meeting_id}").json()

    assert "todos" not in detail
    assert "准备上线材料" not in json.dumps(detail, ensure_ascii=False)


def test_todos_endpoint_returns_todos_separately(tmp_path):
    client = build_client(tmp_path, FakeLLM([LLMResponse(content=WITH_TODOS_JSON)]))
    meeting_id = client.post("/api/meetings/generate", json={"raw_text": "x"}).json()["id"]

    data = client.get(f"/api/todos?meeting_id={meeting_id}").json()

    assert data["count"] == 1
    assert data["todos"][0]["content"] == "准备上线材料"
    assert data["todos"][0]["owner"] == "张三"
    assert data["todos"][0]["meeting_title"] == "产品周会"
