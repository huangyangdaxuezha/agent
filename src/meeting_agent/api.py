"""Web 入口层：FastAPI 服务，与 CLI 共用同一套 AgentLoop，核心逻辑零改动。

- 会话隔离：每个 session 独立记忆与存储文件；
- 纪要持久化：SQLite（会议原文不入库，只存生成结果，见 memory/repository.py）；
- 安全：敏感工具在 Web 下一律拒绝；纪要的查询/修改工具非敏感，自动执行但留 change_log。
"""

from __future__ import annotations

import argparse
import re
import threading
import uuid
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .bootstrap import create_llm, load_dotenv
from .config import Config, load_config
from .core.loop import AgentLoop
from .core.minutes import MinutesGenerator
from .core.prompt import DEFAULT_SYSTEM_PROMPT, TOOL_USAGE_HINT
from .memory.repository import RepositoryError, SQLiteRepository
from .memory.short_term import ConversationMemory
from .memory.store import JsonSessionStore
from .observability.logger import get_logger, setup_logging
from .tools.builtin import register_minutes_tools
from .tools.registry import ToolRegistry, ToolSpec

if TYPE_CHECKING:  # 仅为类型标注，运行时不产生依赖
    from .llm.base import LLMClient
    from .tools.registry import ConfirmFn

logger = get_logger("api")

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
DEFAULT_SESSION_DIR = ".sessions"
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str


class GenerateRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=50000)
    title: str | None = None
    meeting_date: str = ""


class MeetingPatch(BaseModel):
    title: str | None = None
    meeting_date: str | None = None
    content: str | None = None
    summary: str | None = None


def deny_sensitive(spec: ToolSpec, arguments: dict) -> bool:
    """Web 端无人值守，敏感工具一律拒绝，避免误执行。"""
    logger.warning("Web 端拒绝执行敏感工具 %s 参数=%s", spec.name, arguments)
    return False


def validate_session_id(session_id: str) -> str:
    if not SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(status_code=400, detail="非法的 session_id")
    return session_id


def public_meeting(record: dict) -> dict[str, Any]:
    """只暴露对外字段，隐藏内部列。"""
    return {
        "id": record["id"],
        "title": record["title"],
        "meeting_date": record["meeting_date"],
        "summary": record.get("summary") or "",
        "content": record.get("content") or "",
        "todos": record.get("todos") or [],
        "version": record.get("version"),
        "updated_at": record["updated_at"],
    }


def create_app(
    config: Config | None = None,
    llm: "LLMClient | None" = None,
    tools: ToolRegistry | None = None,
    session_dir: str | Path = DEFAULT_SESSION_DIR,
    confirm: "ConfirmFn | None" = None,
    repository: SQLiteRepository | None = None,
) -> FastAPI:
    config = config or load_config()
    llm = llm if llm is not None else create_llm(config)
    repository = repository or SQLiteRepository(config.db_path)
    tools = tools or register_minutes_tools(ToolRegistry(), repository)
    confirm = confirm or deny_sensitive
    session_path = Path(session_dir)
    session_path.mkdir(parents=True, exist_ok=True)
    system_prompt = DEFAULT_SYSTEM_PROMPT + TOOL_USAGE_HINT

    app = FastAPI(title="会议小助手", version="0.2.0")

    def store_for(session_id: str) -> JsonSessionStore:
        return JsonSessionStore(session_path / f"{session_id}.json")

    def build_loop(session_id: str) -> AgentLoop:
        memory = ConversationMemory(max_messages=config.max_history)
        store = store_for(session_id)
        if store.exists():
            for message in store.load():
                memory.add(message)
        return AgentLoop(
            llm=llm,
            memory=memory,
            tools=tools,
            config=config,
            system_prompt=system_prompt,
            confirm=confirm,
            logger=logger.info,
        )

    # ---------- 页面 ----------

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_file = WEB_DIR / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=500, detail="缺少前端文件 web/index.html")
        return FileResponse(index_file)

    # ---------- 对话（模型可调用纪要工具） ----------

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(payload: ChatRequest) -> ChatResponse:
        session_id = validate_session_id(payload.session_id or uuid.uuid4().hex)
        loop = build_loop(session_id)
        reply = loop.run(payload.message)
        store_for(session_id).save(loop.memory.messages)
        return ChatResponse(session_id=session_id, reply=reply)

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict:
        validate_session_id(session_id)
        messages = store_for(session_id).load()
        return {
            "session_id": session_id,
            "messages": [message.to_dict() for message in messages],
        }

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str) -> dict:
        validate_session_id(session_id)
        store_for(session_id).save([])
        return {"session_id": session_id, "cleared": True}

    # ---------- 会议纪要库 ----------

    @app.post("/api/meetings/generate")
    def generate_meeting(payload: GenerateRequest) -> dict:
        """原文 → 纪要 → 直接入库（原文不落库）。"""
        draft = MinutesGenerator(llm).generate(payload.raw_text)
        meeting_id = repository.create_meeting(
            title=payload.title or draft.title, meeting_date=payload.meeting_date
        )
        repository.save_minutes(
            meeting_id,
            content=draft.content,
            summary=draft.summary,
            todos=draft.todos,
            model=config.model or config.provider,
        )
        record = repository.get_meeting(meeting_id)
        result = public_meeting(record or {"id": meeting_id})
        result["structured"] = draft.structured
        result["note"] = draft.note
        logger.info("已保存会议纪要 id=%s structured=%s", meeting_id, draft.structured)
        return result

    @app.get("/api/meetings")
    def list_meetings(keyword: str = "", meeting_date: str = "", limit: int = 20) -> dict:
        rows = repository.search_meetings(
            keyword=keyword, meeting_date=meeting_date, limit=max(1, min(limit, 100))
        )
        return {"count": len(rows), "meetings": [public_meeting(row) for row in rows]}

    @app.get("/api/meetings/{meeting_id}")
    def get_meeting(meeting_id: int) -> dict:
        record = repository.get_meeting(meeting_id)
        if record is None:
            raise HTTPException(status_code=404, detail="会议不存在")
        return public_meeting(record)

    @app.patch("/api/meetings/{meeting_id}")
    def patch_meeting(meeting_id: int, payload: MeetingPatch) -> dict:
        try:
            record = repository.patch_meeting(
                meeting_id,
                title=payload.title,
                meeting_date=payload.meeting_date,
                content=payload.content,
                summary=payload.summary,
            )
        except RepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return public_meeting(record)

    @app.get("/api/meetings/{meeting_id}/changes")
    def meeting_changes(meeting_id: int) -> dict:
        return {"meeting_id": meeting_id, "changes": repository.changes(meeting_id)}

    @app.get("/api/info")
    def info() -> dict:
        """只暴露非敏感信息，绝不返回 api_key。"""
        return {
            "provider": config.provider,
            "model": config.model or "echo-placeholder",
            "base_url": config.base_url,
            "max_steps": config.max_steps,
        }

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meeting-agent-web", description="会议小助手 Web 服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    parser.add_argument("--port", type=int, default=8000, help="端口，默认 8000")
    parser.add_argument("--session-dir", dest="session_dir", default=DEFAULT_SESSION_DIR)
    parser.add_argument("--db", dest="db_path", help="SQLite 文件路径，默认 .data/meeting.db")
    parser.add_argument("--open", dest="open_browser", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--log-level", dest="log_level", help="日志级别")
    args = parser.parse_args(argv)

    load_dotenv()
    config = load_config(log_level=args.log_level, db_path=args.db_path)
    setup_logging(config.log_level)
    app = create_app(config=config, session_dir=args.session_dir)

    url = f"http://{args.host}:{args.port}/"
    if args.open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    logger.info("Web 服务启动：%s（数据库 %s）", url, config.db_path)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
