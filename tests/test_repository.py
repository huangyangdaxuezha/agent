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


def test_todos_table_is_reserved_for_future_module(tmp_path):
    repo = make_repo(tmp_path)
    meeting_id = new_meeting(repo)

    with sqlite3.connect(str(tmp_path / "test.db")) as conn:
        conn.execute(
            "INSERT INTO todos (meeting_id, content, owner, due_date, status, created_at)"
            " VALUES (?, ?, ?, ?, 'open', '2026-10-20T00:00:00')",
            (meeting_id, "准备上线材料", "张三", "2026-10-25"),
        )
        count = conn.execute("SELECT COUNT(*) FROM todos").fetchone()[0]

    assert count == 1
