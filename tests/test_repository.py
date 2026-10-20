import sqlite3

from meeting_agent.memory.repository import RepositoryError, SQLiteRepository


def make_repo(tmp_path) -> SQLiteRepository:
    return SQLiteRepository(tmp_path / "test.db")


def new_meeting(repo: SQLiteRepository, title: str = "周会", date: str = "2026-10-20") -> int:
    meeting_id = repo.create_meeting(title=title, meeting_date=date)
    repo.save_minutes(meeting_id, content="## 结论\n确定下周一上线", summary="上线时间确定")
    return meeting_id


def test_create_and_get(tmp_path):
    repo = make_repo(tmp_path)
    meeting_id = new_meeting(repo)

    record = repo.get_meeting(meeting_id)
    assert record is not None
    assert record["title"] == "周会"
    assert record["meeting_date"] == "2026-10-20"
    assert "下周一上线" in record["content"]
    assert record["is_current"] == 1


def test_get_missing_returns_none(tmp_path):
    assert make_repo(tmp_path).get_meeting(999) is None


def test_save_minutes_creates_new_version(tmp_path):
    repo = make_repo(tmp_path)
    meeting_id = new_meeting(repo)

    repo.save_minutes(meeting_id, content="## 结论\n改为下周二上线", summary="时间调整")

    record = repo.get_meeting(meeting_id)
    assert record["version"] == 2
    assert "下周二" in record["content"]
    assert len(repo.list_versions(meeting_id)) == 2


def test_search_by_keyword(tmp_path):
    repo = make_repo(tmp_path)
    new_meeting(repo, title="预算评审", date="2026-10-18")
    other = repo.create_meeting(title="技术复盘", meeting_date="2026-10-19")
    repo.save_minutes(other, content="讨论了性能问题")

    assert [r["title"] for r in repo.search_meetings(keyword="预算")] == ["预算评审"]
    assert len(repo.search_meetings(keyword="性能")) == 1
    assert len(repo.search_meetings(meeting_date="2026-10-19")) == 1


def test_patch_only_touches_given_fields(tmp_path):
    repo = make_repo(tmp_path)
    meeting_id = new_meeting(repo)

    updated = repo.patch_meeting(meeting_id, title="周会（已确认）")

    assert updated["title"] == "周会（已确认）"
    assert updated["meeting_date"] == "2026-10-20"
    assert "下周一上线" in updated["content"]


def test_patch_records_change_log(tmp_path):
    repo = make_repo(tmp_path)
    meeting_id = new_meeting(repo)

    repo.patch_meeting(meeting_id, title="新标题")

    changes = repo.changes(meeting_id)
    assert changes[0]["field"] == "title"
    assert changes[0]["old_value"] == "周会"
    assert changes[0]["new_value"] == "新标题"


def test_patch_unknown_meeting_raises(tmp_path):
    repo = make_repo(tmp_path)
    try:
        repo.patch_meeting(123, title="x")
    except RepositoryError:
        pass
    else:
        raise AssertionError("不存在的会议应抛 RepositoryError")


def test_rollback_restores_previous_version(tmp_path):
    repo = make_repo(tmp_path)
    meeting_id = new_meeting(repo)
    repo.save_minutes(meeting_id, content="第二版内容")

    assert repo.rollback(meeting_id, 1) is True
    assert "下周一上线" in repo.get_meeting(meeting_id)["content"]
    assert repo.rollback(meeting_id, 99) is False


def test_raw_text_is_not_persisted(tmp_path):
    """需求：会议原文不入库。"""
    repo = make_repo(tmp_path)
    new_meeting(repo)

    with sqlite3.connect(str(tmp_path / "test.db")) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(meetings)")
        } | {row[1] for row in conn.execute("PRAGMA table_info(minutes)")}

    assert "raw_text" not in columns
    assert "content" in columns


def test_minutes_and_todos_live_in_separate_tables(tmp_path):
    """分表要求：待办不写在 minutes 里，查纪要也拿不到待办。"""
    repo = make_repo(tmp_path)
    meeting_id = repo.create_meeting(title="周会", meeting_date="2026-10-20")
    repo.save_minutes(
        meeting_id,
        content="## 结论\n下周一上线",
        summary="上线确定",
        todos=[{"content": "准备上线材料", "owner": "张三", "due_date": "2026-10-25"}],
    )

    record = repo.get_meeting(meeting_id)
    assert "todos" not in record
    assert record["content"] == "## 结论\n下周一上线"

    with sqlite3.connect(str(tmp_path / "test.db")) as conn:
        minutes_columns = {row[1] for row in conn.execute("PRAGMA table_info(minutes)")}
        todos_count = conn.execute("SELECT COUNT(*) FROM todos").fetchone()[0]

    assert "todos" not in minutes_columns
    assert todos_count == 1


def test_list_todos_returns_meeting_context(tmp_path):
    repo = make_repo(tmp_path)
    meeting_id = repo.create_meeting(title="周会", meeting_date="2026-10-20")
    repo.save_minutes(
        meeting_id,
        content="正文",
        todos=[
            {"content": "准备材料", "owner": "张三", "due_date": "2026-10-25"},
            {"content": "通知客户", "owner": ""},
        ],
    )

    todos = repo.list_todos()

    assert [t["content"] for t in todos] == ["准备材料", "通知客户"]
    assert todos[0]["meeting_title"] == "周会"
    assert todos[0]["status"] == "open"
    assert todos[0]["owner"] == "张三"


def test_list_todos_filters_by_meeting_and_status(tmp_path):
    repo = make_repo(tmp_path)
    first = repo.create_meeting(title="A")
    second = repo.create_meeting(title="B")
    repo.save_minutes(first, content="a", todos=[{"content": "A 的待办"}])
    repo.save_minutes(second, content="b", todos=[{"content": "B 的待办"}])

    assert [t["content"] for t in repo.list_todos(meeting_id=first)] == ["A 的待办"]
    assert repo.list_todos(status="done") == []


def test_regenerating_minutes_replaces_todos(tmp_path):
    """重新生成纪要时待办整体覆盖，不会越堆越多。"""
    repo = make_repo(tmp_path)
    meeting_id = repo.create_meeting(title="周会")
    repo.save_minutes(meeting_id, content="第一版", todos=[{"content": "旧待办"}])

    repo.save_minutes(meeting_id, content="第二版", todos=[{"content": "新待办"}])

    assert [t["content"] for t in repo.list_todos(meeting_id=meeting_id)] == ["新待办"]


def test_missing_todos_argument_keeps_existing_todos(tmp_path):
    repo = make_repo(tmp_path)
    meeting_id = repo.create_meeting(title="周会")
    repo.save_minutes(meeting_id, content="第一版", todos=[{"content": "保留的待办"}])

    repo.save_minutes(meeting_id, content="第二版")

    assert [t["content"] for t in repo.list_todos()] == ["保留的待办"]


def test_legacy_todos_column_is_migrated(tmp_path):
    """旧库（待办是 minutes.todos 里的 JSON）升级后自动搬到独立表。"""
    db = tmp_path / "legacy.db"
    with sqlite3.connect(str(db)) as conn:
        conn.executescript(
            """
            CREATE TABLE meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                meeting_date TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT 'local',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE minutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                version INTEGER NOT NULL DEFAULT 1,
                summary TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                todos TEXT NOT NULL DEFAULT '[]',
                model TEXT NOT NULL DEFAULT '',
                is_current INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            INSERT INTO meetings (title, meeting_date, created_at, updated_at)
                VALUES ('旧会议', '2026-10-01', 't', 't');
            INSERT INTO minutes (meeting_id, version, summary, content, todos, model, is_current, created_at)
                VALUES (1, 1, '', '旧正文',
                        '[{"content":"跟进预算","owner":"李四","due_date":"2026-10-30"}]',
                        'm', 1, 't');
            """
        )

    repo = SQLiteRepository(db)

    assert [t["content"] for t in repo.list_todos()] == ["跟进预算"]
    record = repo.get_meeting(1)
    assert record["content"] == "旧正文"
    assert "todos" not in record

    with sqlite3.connect(str(db)) as conn:
        minutes_columns = {row[1] for row in conn.execute("PRAGMA table_info(minutes)")}
    assert "todos" not in minutes_columns
