import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(
    conn: sqlite3.Connection,
    account_id: int,
    year: int,
    frozen_kwh: float,
    note: str | None = None,
) -> dict:
    """Write a freeze snapshot. Any prior active freeze for the same
    account/year is closed first, so at most one freeze point is active."""
    conn.execute(
        """
        UPDATE tier_freezes SET unfrozen_at=?
        WHERE account_id=? AND year=? AND unfrozen_at IS NULL
        """,
        (_now(), account_id, year),
    )
    cur = conn.execute(
        """
        INSERT INTO tier_freezes(account_id, year, frozen_kwh, frozen_at, note, unfrozen_at)
        VALUES (?,?,?,?,?,NULL)
        """,
        (account_id, year, float(frozen_kwh), _now(), note),
    )
    conn.commit()
    return get(conn, int(cur.lastrowid))


def get(conn: sqlite3.Connection, freeze_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM tier_freezes WHERE id=?", (freeze_id,)).fetchone()
    return dict(row) if row else None


def active(conn: sqlite3.Connection, account_id: int, year: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM tier_freezes
        WHERE account_id=? AND year=? AND unfrozen_at IS NULL
        ORDER BY id DESC LIMIT 1
        """,
        (account_id, year),
    ).fetchone()
    return dict(row) if row else None


def list_for_year(conn: sqlite3.Connection, account_id: int, year: int) -> list[dict]:
    q = """
        SELECT * FROM tier_freezes
        WHERE account_id=? AND year=? ORDER BY id
    """
    return [dict(r) for r in conn.execute(q, (account_id, year)).fetchall()]


def unfreeze(conn: sqlite3.Connection, account_id: int, year: int) -> dict | None:
    row = active(conn, account_id, year)
    if not row:
        return None
    conn.execute(
        "UPDATE tier_freezes SET unfrozen_at=? WHERE id=?",
        (_now(), row["id"]),
    )
    conn.commit()
    return get(conn, row["id"])
