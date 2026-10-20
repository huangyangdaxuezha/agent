"""SQLite 仓储：会议纪要与待办的长期持久化（demo 规模：本机单文件）。

设计约定：
- 会议原文**不入库**（用完即弃），只持久化生成的纪要与元信息；
- 纪要按版本保存，最新一版 is_current=1，可回滚；
- 字段级修改走 patch_meeting，并把改动写进 change_log（改错了能查到）；
- **纪要与待办分表**：minutes 只存纪要正文，待办存独立 todos 表，
  因此查纪要时不会带出任何待办数据；待办模块可以独立演进，不动纪要表结构；
- 旧库（todos 曾以 JSON 存在 minutes.todos 里）会自动迁移到 todos 表；
- 所有 SQL 只出现在本文件，将来换 Postgres/MySQL 时只改这里。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = ".data/meeting.db"

MINUTES_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS minutes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
        version INTEGER NOT NULL DEFAULT 1,
        summary TEXT NOT NULL DEFAULT '',
        content TEXT NOT NULL,
        model TEXT NOT NULL DEFAULT '',
        is_current INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """

MINUTES_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_minutes_meeting ON minutes(meeting_id, is_current)"

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL DEFAULT '',
        meeting_date TEXT NOT NULL DEFAULT '',
        owner TEXT NOT NULL DEFAULT 'local',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    MINUTES_TABLE_SQL,
    # 待办独立表：与纪要分开存，查纪要不会读到待办
    """
    CREATE TABLE IF NOT EXISTS todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        owner TEXT NOT NULL DEFAULT '',
        due_date TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER NOT NULL,
        field TEXT NOT NULL,
        old_value TEXT NOT NULL DEFAULT '',
        new_value TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    MINUTES_INDEX_SQL,
    "CREATE INDEX IF NOT EXISTS idx_todos_meeting ON todos(meeting_id)",
)


class RepositoryError(RuntimeError):
    """仓储层异常。"""


def timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SQLiteRepository:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        parent = self.db_path.parent
        if str(parent) not in {"", "."}:
            parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            for statement in SCHEMA_STATEMENTS:
                conn.execute(statement)
            self._migrate_split_todos(conn)

    @staticmethod
    def _migrate_split_todos(conn: sqlite3.Connection) -> None:
        """旧库把待办以 JSON 存在 minutes.todos，这里搬到独立表并去掉该列。

        只跑一次：迁移后 minutes 表不再有 todos 列，下次启动直接跳过。
        """
        columns = {row[1] for row in conn.execute("PRAGMA table_info(minutes)")}
        if "todos" not in columns:
            return

        rows = conn.execute("SELECT meeting_id, todos, created_at FROM minutes").fetchall()
        for meeting_id, payload, created_at in rows:
            try:
                items = json.loads(payload or "[]")
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, str):
                    item = {"content": item}
                if not isinstance(item, dict):
                    continue
                content = str(item.get("content", "")).strip()
                if not content:
                    continue
                conn.execute(
                    "INSERT INTO todos (meeting_id, content, owner, due_date, status, created_at)"
                    " VALUES (?, ?, ?, ?, 'open', ?)",
                    (
                        meeting_id,
                        content,
                        str(item.get("owner", "")).strip(),
                        str(item.get("due_date", "")).strip(),
                        created_at or timestamp(),
                    ),
                )

        # SQLite 的 DROP COLUMN 对旧版本不可用，统一用「重建表」的方式去掉列
        conn.execute("DROP INDEX IF EXISTS idx_minutes_meeting")
        conn.execute("ALTER TABLE minutes RENAME TO minutes_legacy")
        conn.execute(MINUTES_TABLE_SQL)
        conn.execute(
            "INSERT INTO minutes (id, meeting_id, version, summary, content, model,"
            " is_current, created_at)"
            " SELECT id, meeting_id, version, summary, content, model, is_current, created_at"
            " FROM minutes_legacy"
        )
        conn.execute("DROP TABLE minutes_legacy")
        conn.execute(MINUTES_INDEX_SQL)

    # ---------- 写入 ----------

    def create_meeting(
        self,
        title: str,
        meeting_date: str = "",
        owner: str = "local",
    ) -> int:
        ts = timestamp()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO meetings (title, meeting_date, owner, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (title, meeting_date, owner, ts, ts),
            )
            return int(cursor.lastrowid)

    def save_minutes(
        self,
        meeting_id: int,
        content: str,
        summary: str = "",
        todos: list[dict] | None = None,
        model: str = "",
    ) -> int:
        """保存一版纪要；旧版本保留（is_current=0），便于回滚。

        待办写独立的 todos 表，与纪要不在一张表里：
        - `todos=None` 表示不碰已有待办；
        - `todos=[]` 表示清空该会议的待办；
        - 传入列表则整体覆盖（重新生成纪要不会把旧待办越堆越多）。
        """
        ts = timestamp()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS v FROM minutes WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()
            version = int(row["v"]) + 1
            conn.execute(
                "UPDATE minutes SET is_current = 0 WHERE meeting_id = ?", (meeting_id,)
            )
            cursor = conn.execute(
                "INSERT INTO minutes (meeting_id, version, summary, content, model,"
                " is_current, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (meeting_id, version, summary, content, model, ts),
            )
            conn.execute(
                "UPDATE meetings SET updated_at = ? WHERE id = ?", (ts, meeting_id)
            )
            if todos is not None:
                self._replace_todos(conn, meeting_id, todos, ts)
            return int(cursor.lastrowid)

    @staticmethod
    def _replace_todos(
        conn: sqlite3.Connection, meeting_id: int, todos: list[dict], ts: str
    ) -> None:
        conn.execute("DELETE FROM todos WHERE meeting_id = ?", (meeting_id,))
        for item in todos:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            conn.execute(
                "INSERT INTO todos (meeting_id, content, owner, due_date, status, created_at)"
                " VALUES (?, ?, ?, ?, 'open', ?)",
                (
                    meeting_id,
                    content,
                    str(item.get("owner", "")).strip(),
                    str(item.get("due_date", "")).strip(),
                    ts,
                ),
            )

    def patch_meeting(
        self,
        meeting_id: int,
        title: str | None = None,
        meeting_date: str | None = None,
        content: str | None = None,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """字段级修改：只改传入的字段，其余保持原值，并记录 change_log。"""
        record = self.get_meeting(meeting_id)
        if record is None:
            raise RepositoryError(f"会议不存在：{meeting_id}")

        ts = timestamp()
        with self._connect() as conn:
            for field, value, table in (
                ("title", title, "meetings"),
                ("meeting_date", meeting_date, "meetings"),
                ("content", content, "minutes"),
                ("summary", summary, "minutes"),
            ):
                if value is None:
                    continue
                old_value = str(record.get(field) or "")
                if old_value == value:
                    continue
                conn.execute(
                    "INSERT INTO change_log (meeting_id, field, old_value, new_value, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (meeting_id, field, old_value, value, ts),
                )
                if table == "meetings":
                    conn.execute(
                        f"UPDATE meetings SET {field} = ?, updated_at = ? WHERE id = ?",
                        (value, ts, meeting_id),
                    )
                else:
                    conn.execute(
                        f"UPDATE minutes SET {field} = ?"
                        " WHERE meeting_id = ? AND is_current = 1",
                        (value, meeting_id),
                    )
                    conn.execute(
                        "UPDATE meetings SET updated_at = ? WHERE id = ?", (ts, meeting_id)
                    )

        updated = self.get_meeting(meeting_id)
        assert updated is not None
        return updated

    # ---------- 查询 ----------

    def get_meeting(self, meeting_id: int) -> dict[str, Any] | None:
        """只返回纪要本身；待办在独立表，不会混进来。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT m.*, mi.id AS minutes_id, mi.version, mi.summary, mi.content,"
                " mi.model, mi.is_current FROM meetings m"
                " LEFT JOIN minutes mi ON mi.meeting_id = m.id AND mi.is_current = 1"
                " WHERE m.id = ?",
                (meeting_id,),
            ).fetchone()
        return self._to_record(row) if row else None

    def search_meetings(
        self, keyword: str = "", meeting_date: str = "", limit: int = 20
    ) -> list[dict[str, Any]]:
        """关键词命中标题/摘要/正文；demo 规模用 LIKE 足够。"""
        like = f"%{keyword}%" if keyword else ""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT m.*, mi.id AS minutes_id, mi.version, mi.summary, mi.content,"
                " mi.model, mi.is_current FROM meetings m"
                " LEFT JOIN minutes mi ON mi.meeting_id = m.id AND mi.is_current = 1"
                " WHERE (? = '' OR m.title LIKE ? OR mi.summary LIKE ? OR mi.content LIKE ?)"
                "   AND (? = '' OR m.meeting_date = ?)"
                " ORDER BY m.updated_at DESC, m.id DESC LIMIT ?",
                (keyword, like, like, like, meeting_date, meeting_date, limit),
            ).fetchall()
        return [self._to_record(row) for row in rows]

    def list_meetings(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.search_meetings(limit=limit)

    def list_versions(self, meeting_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, version, is_current, created_at FROM minutes"
                " WHERE meeting_id = ? ORDER BY version DESC",
                (meeting_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def rollback(self, meeting_id: int, version: int) -> bool:
        """把指定版本设为当前版本（旧版本一直保留，不会丢数据）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM minutes WHERE meeting_id = ? AND version = ?",
                (meeting_id, version),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE minutes SET is_current = 0 WHERE meeting_id = ?", (meeting_id,)
            )
            conn.execute("UPDATE minutes SET is_current = 1 WHERE id = ?", (row["id"],))
        return True

    def changes(self, meeting_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT field, old_value, new_value, created_at FROM change_log"
                " WHERE meeting_id = ? ORDER BY id DESC",
                (meeting_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ---------- 待办（独立表，与纪要互不干扰） ----------

    def list_todos(
        self, meeting_id: int | None = None, status: str = "", limit: int = 100
    ) -> list[dict[str, Any]]:
        """按会议 / 状态查待办；带上会议标题与日期，方便直接展示。"""
        sql = (
            "SELECT t.id, t.meeting_id, t.content, t.owner, t.due_date, t.status,"
            " t.created_at, m.title AS meeting_title, m.meeting_date"
            " FROM todos t JOIN meetings m ON m.id = t.meeting_id WHERE 1 = 1"
        )
        params: list[Any] = []
        if meeting_id is not None:
            sql += " AND t.meeting_id = ?"
            params.append(int(meeting_id))
        if status:
            sql += " AND t.status = ?"
            params.append(status)
        sql += " ORDER BY (t.due_date = ''), t.due_date, t.id LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _to_record(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)
