import json
import sqlite3
from datetime import datetime, timezone


def insert(
    conn: sqlite3.Connection,
    kind: str,
    payload: dict,
    result: dict,
    account_id: int | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
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


_YEAR_EXPR = "CAST(substr(created_at, 1, 4) AS INTEGER)"


def yearly_billed_kwh(conn: sqlite3.Connection, account_id: int, year: int) -> float:
    """Sum of net energy from persisted bill runs in the natural year."""
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(COALESCE(
            json_extract(result_json, '$.kwh'),
            json_extract(input_json, '$.kwh')
        )), 0) AS total
        FROM calc_runs
        WHERE kind='bill' AND account_id=? AND {_YEAR_EXPR}=?
        """,
        (account_id, year),
    ).fetchone()
    return round(float(row["total"]), 3)


def yearly_bill_details(conn: sqlite3.Connection, account_id: int, year: int) -> list[dict]:
    """Persisted bill-run details that make up the yearly accumulated energy."""
    q = f"""
        SELECT id AS run_id, created_at,
               COALESCE(json_extract(result_json, '$.kwh'),
                        json_extract(input_json, '$.kwh')) AS kwh
        FROM calc_runs
        WHERE kind='bill' AND account_id=? AND {_YEAR_EXPR}=?
        ORDER BY id
    """
    return [dict(r) for r in conn.execute(q, (account_id, year)).fetchall()]
