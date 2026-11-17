"""持久化：sqlite 单文件，够用就好。

刻意不引入 ORM —— 平台早期最不需要的就是「表结构比用例还复杂」。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from atp.config import settings
from atp.models import DraftResult, RunRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    trigger     TEXT NOT NULL,
    selector    TEXT,
    status      TEXT NOT NULL,
    total       INTEGER DEFAULT 0,
    passed      INTEGER DEFAULT 0,
    failed      INTEGER DEFAULT 0,
    skipped     INTEGER DEFAULT 0,
    duration    REAL DEFAULT 0,
    pass_rate   REAL DEFAULT 0,
    report_path TEXT,
    payload     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    requirement TEXT NOT NULL,
    provider    TEXT,
    valid       INTEGER DEFAULT 0,
    files       TEXT,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.db_file)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def save_run(record: RunRecord) -> int:
    init_db()
    with connect() as conn:
        cursor = conn.execute(
            """INSERT INTO runs
               (created_at, trigger, selector, status, total, passed, failed, skipped,
                duration, pass_rate, report_path, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.created_at,
                record.trigger,
                record.selector,
                record.status,
                record.total,
                record.passed,
                record.failed,
                record.skipped,
                record.duration,
                record.pass_rate,
                record.report_path,
                record.model_dump_json(),
            ),
        )
        record.id = int(cursor.lastrowid or 0)
        # 回填 id 后再存一次，保证读出来就带 id
        conn.execute("UPDATE runs SET payload = ? WHERE id = ?", (record.model_dump_json(), record.id))
    return record.id


def update_run(record: RunRecord) -> None:
    """运行结束后回填报告路径等字段（id 由 save_run 分配）。"""
    if not record.id:
        save_run(record)
        return
    with connect() as conn:
        conn.execute(
            """UPDATE runs SET status = ?, total = ?, passed = ?, failed = ?, skipped = ?,
                   duration = ?, pass_rate = ?, report_path = ?, payload = ?
               WHERE id = ?""",
            (
                record.status,
                record.total,
                record.passed,
                record.failed,
                record.skipped,
                record.duration,
                record.pass_rate,
                record.report_path,
                record.model_dump_json(),
                record.id,
            ),
        )


def list_runs(limit: int = 20) -> list[RunRecord]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [RunRecord.model_validate_json(row["payload"]) for row in rows]


def get_run(run_id: int) -> RunRecord | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
    return RunRecord.model_validate_json(row["payload"]) if row else None


def latest_run() -> RunRecord | None:
    runs = list_runs(limit=1)
    return runs[0] if runs else None


def save_draft(draft: DraftResult) -> int:
    init_db()
    from atp.models import now_iso

    with connect() as conn:
        cursor = conn.execute(
            """INSERT INTO drafts (created_at, requirement, provider, valid, files, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                now_iso(),
                draft.requirement,
                draft.provider,
                int(draft.valid),
                json.dumps(draft.files, ensure_ascii=False),
                json.dumps(draft.notes + draft.errors, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid or 0)


def list_drafts(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, requirement, provider, valid, notes FROM drafts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_kv(key: str, value: Any) -> None:
    init_db()
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    with connect() as conn:
        conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, payload),
        )


def get_kv(key: str, default: Any = None) -> Any:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except (TypeError, json.JSONDecodeError):
        return row["value"]