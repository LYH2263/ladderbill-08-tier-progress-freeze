import sqlite3
from datetime import datetime, timezone


def insert(
    conn: sqlite3.Connection,
    account_id: int,
    year: int,
    frozen_kwh: float,
    year_kwh: float,
    run_id: int | None = None,
    note: str | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO freeze_points(
            account_id, year, frozen_kwh, year_kwh, status, run_id, note, created_at)
        VALUES (?,?,?,?, 'frozen', ?, ?, ?)
        """,
        (account_id, year, float(frozen_kwh), float(year_kwh), run_id, note, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def active_freeze(conn: sqlite3.Connection, account_id: int, year: int) -> dict | None:
    """当前生效（未解冻）的冻结点。"""
    row = conn.execute(
        """
        SELECT * FROM freeze_points
        WHERE account_id=? AND year=? AND status='frozen'
        ORDER BY id DESC LIMIT 1
        """,
        (account_id, year),
    ).fetchone()
    return dict(row) if row else None


def unfreeze(conn: sqlite3.Connection, freeze_id: int) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE freeze_points SET status='unfrozen', unfrozen_at=? WHERE id=? AND status='frozen'",
        (now, freeze_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get(conn, freeze_id)


def get(conn: sqlite3.Connection, freeze_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM freeze_points WHERE id=?", (freeze_id,)).fetchone()
    return dict(row) if row else None


def list_for_account_year(conn: sqlite3.Connection, account_id: int, year: int) -> list[dict]:
    q = """
    SELECT * FROM freeze_points
    WHERE account_id=? AND year=? ORDER BY id
    """
    return [dict(r) for r in conn.execute(q, (account_id, year)).fetchall()]


def list_for_account(conn: sqlite3.Connection, account_id: int, limit: int = 20) -> list[dict]:
    q = "SELECT * FROM freeze_points WHERE account_id=? ORDER BY id DESC LIMIT ?"
    return [dict(r) for r in conn.execute(q, (account_id, limit)).fetchall()]
