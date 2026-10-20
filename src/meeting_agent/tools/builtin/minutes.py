"""会议纪要工具：让模型能自己查库、改库（用户场景：问纪要 → 改标题）。

这些工具**不标记 sensitive**：按需求，生成与修改都要自动完成，不弹确认。
安全兜底靠两点：只做字段级修改、所有改动进 change_log 可追溯可回滚。
"""

from __future__ import annotations

import json

from ...memory.repository import SQLiteRepository
from ..registry import ToolRegistry


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


def _dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False)


def register_minutes_tools(
    registry: ToolRegistry, repository: SQLiteRepository
) -> ToolRegistry:
    @registry.register(
        name="list_meetings",
        description="查询会议纪要列表，可按关键词（标题/摘要/正文）或日期过滤，返回 id、标题、日期",
        parameters=_schema(
            {
                "keyword": {"type": "string", "description": "关键词，空则不过滤"},
                "meeting_date": {"type": "string", "description": "会议日期，如 2026-10-20"},
                "limit": {"type": "integer", "description": "返回条数，默认 10"},
            }
        ),
    )
    def list_meetings(keyword: str = "", meeting_date: str = "", limit: int = 10) -> str:
        rows = repository.search_meetings(
            keyword=keyword, meeting_date=meeting_date, limit=max(1, min(int(limit), 50))
        )
        brief = [
            {
                "id": row["id"],
                "title": row["title"],
                "meeting_date": row["meeting_date"],
                "summary": row.get("summary") or "",
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
        return _dump({"count": len(brief), "meetings": brief})

    @registry.register(
        name="get_meeting_minutes",
        description="按 id 获取某场会议的纪要（标题、日期、摘要、正文）；不含待办，待办用 list_todos 查",
        parameters=_schema({"meeting_id": {"type": "integer"}}, ["meeting_id"]),
    )
    def get_meeting_minutes(meeting_id: int) -> str:
        record = repository.get_meeting(int(meeting_id))
        if record is None:
            return _dump({"error": f"未找到会议 {meeting_id}"})
        return _dump(
            {
                "id": record["id"],
                "title": record["title"],
                "meeting_date": record["meeting_date"],
                "summary": record.get("summary") or "",
                "content": record.get("content") or "",
                "version": record.get("version"),
            }
        )

    @registry.register(
        name="list_todos",
        description="查询待办事项（与纪要分开存储），可按会议 id 或状态过滤；不传 meeting_id 表示查全部",
        parameters=_schema(
            {
                "meeting_id": {"type": "integer", "description": "会议 id，0 表示不限"},
                "status": {"type": "string", "description": "状态，如 open / done，空则不过滤"},
                "limit": {"type": "integer", "description": "返回条数，默认 20"},
            }
        ),
    )
    def list_todos(meeting_id: int = 0, status: str = "", limit: int = 20) -> str:
        rows = repository.list_todos(
            meeting_id=int(meeting_id) or None,
            status=status,
            limit=max(1, min(int(limit), 100)),
        )
        return _dump({"count": len(rows), "todos": rows})

    @registry.register(
        name="update_meeting",
        description="修改会议纪要的字段；只传需要改的字段，其余保持原值",
        parameters=_schema(
            {
                "meeting_id": {"type": "integer"},
                "title": {"type": "string", "description": "新的会议标题"},
                "meeting_date": {"type": "string", "description": "会议日期"},
                "content": {"type": "string", "description": "纪要正文（Markdown）"},
                "summary": {"type": "string", "description": "一句话摘要"},
            },
            ["meeting_id"],
        ),
    )
    def update_meeting(
        meeting_id: int,
        title: str | None = None,
        meeting_date: str | None = None,
        content: str | None = None,
        summary: str | None = None,
    ) -> str:
        updated = repository.patch_meeting(
            int(meeting_id),
            title=title,
            meeting_date=meeting_date,
            content=content,
            summary=summary,
        )
        return _dump(
            {
                "ok": True,
                "id": updated["id"],
                "title": updated["title"],
                "meeting_date": updated["meeting_date"],
                "summary": updated.get("summary") or "",
                "version": updated.get("version"),
            }
        )

    @registry.register(
        name="save_meeting_minutes",
        description="把一份新的会议纪要存入数据库（会生成新版本，旧版本保留可回滚）",
        parameters=_schema(
            {
                "title": {"type": "string"},
                "content": {"type": "string", "description": "纪要正文（Markdown）"},
                "summary": {"type": "string"},
                "meeting_date": {"type": "string"},
            },
            ["title", "content"],
        ),
    )
    def save_meeting_minutes(
        title: str, content: str, summary: str = "", meeting_date: str = ""
    ) -> str:
        meeting_id = repository.create_meeting(title=title, meeting_date=meeting_date)
        minutes_id = repository.save_minutes(meeting_id, content=content, summary=summary)
        return _dump({"ok": True, "meeting_id": meeting_id, "minutes_id": minutes_id})

    return registry
