"""Web 入口层：FastAPI 服务，与 CLI 共用同一套 AgentLoop，核心逻辑零改动。

并发：每个 session 独立记忆与存储文件，请求内重建，避免多用户串台。
安全：Web 端无法同步等待人工点击，敏感工具默认一律拒绝（见 deny_sensitive）。
"""

from __future__ import annotations

import argparse
import re
import threading
import uuid
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .bootstrap import create_llm, load_dotenv
from .config import Config, load_config
from .core.loop import AgentLoop
from .core.prompt import DEFAULT_SYSTEM_PROMPT
from .memory.short_term import ConversationMemory
from .memory.store import JsonSessionStore
from .observability.logger import get_logger, setup_logging
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


def deny_sensitive(spec: ToolSpec, arguments: dict) -> bool:
    """Web 端无人值守，敏感工具一律拒绝，避免误执行。"""
    logger.warning("Web 端拒绝执行敏感工具 %s 参数=%s", spec.name, arguments)
    return False


def validate_session_id(session_id: str) -> str:
    if not SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(status_code=400, detail="非法的 session_id")
    return session_id


def create_app(
    config: Config | None = None,
    llm: "LLMClient | None" = None,
    tools: ToolRegistry | None = None,
    session_dir: str | Path = DEFAULT_SESSION_DIR,
    confirm: "ConfirmFn | None" = None,
) -> FastAPI:
    config = config or load_config()
    llm = llm if llm is not None else create_llm(config)
    tools = tools or ToolRegistry()
    confirm = confirm or deny_sensitive
    session_path = Path(session_dir)
    session_path.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="会议小助手", version="0.1.0")

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
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            confirm=confirm,
            logger=logger.info,
        )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_file = WEB_DIR / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=500, detail="缺少前端文件 web/index.html")
        return FileResponse(index_file)

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
    parser.add_argument("--open", dest="open_browser", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--log-level", dest="log_level", help="日志级别")
    args = parser.parse_args(argv)

    load_dotenv()
    config = load_config(log_level=args.log_level)
    setup_logging(config.log_level)
    app = create_app(config=config, session_dir=args.session_dir)

    url = f"http://{args.host}:{args.port}/"
    if args.open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    logger.info("Web 服务启动：%s", url)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
