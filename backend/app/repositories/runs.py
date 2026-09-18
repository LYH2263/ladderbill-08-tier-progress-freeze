import json
import sqlite3
from datetime import datetime, timezone


def insert(
    conn: sqlite3.Connection,
    kind: str,
    payload: dict,
    result: dict,
    account_id: int | None = None,
    created_at: str | None = None,
) -> int:
    now = created_at or datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO calc_runs(kind, account_id, input_json, result_json, created_at)
        VALUES (?,?,?,?,?)
        """,
        (kind, account_id, json.dumps(payload, ensure_ascii=False), json.dumps(result, ensure_ascii=False), now),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_recent(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    q = """
    SELECT id, kind, account_id, input_json, result_json, created_at
    FROM calc_runs ORDER BY id DESC LIMIT ?
    """
    return [dict(r) for r in conn.execute(q, (limit,)).fetchall()]


def get(conn: sqlite3.Connection, run_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM calc_runs WHERE id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def bill_rows_for_account(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    """该户全部已落库计费(bill)运行，按 id 正序。

    自然年归属由服务层按 input_json.year（缺省回退 created_at 年份）判定。
    """
    q = """
    SELECT id, kind, account_id, input_json, result_json, created_at
    FROM calc_runs
    WHERE account_id=? AND kind='bill'
    ORDER BY id
    """
    return [dict(r) for r in conn.execute(q, (account_id,)).fetchall()]
