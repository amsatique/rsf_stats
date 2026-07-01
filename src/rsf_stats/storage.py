"""SQLite persistence: completion history, personal-best tracking, followed drivers.

Deliberately tiny and dependency-free (stdlib ``sqlite3``). A fresh connection is
opened per call, so it is safe to use from FastAPI's threadpool.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from .models import Rival, StatsSnapshot, time_to_seconds

# Keep the completion history meaningful without bloating: record a new snapshot
# only when completion changed or enough time passed, and keep a bounded window.
SNAPSHOT_MIN_INTERVAL = 3600.0  # seconds
MAX_SNAPSHOTS = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    driver_id  INTEGER,
    fetched_at REAL,
    done_count INTEGER,
    total      INTEGER
);
CREATE TABLE IF NOT EXISTS stage_times (
    driver_id      INTEGER,
    stage_id       INTEGER,
    stage_name     TEXT,
    reference_time TEXT,
    seconds        REAL,
    recorded_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_stage_times ON stage_times (driver_id, stage_id);
CREATE TABLE IF NOT EXISTS rivals (
    user_id  INTEGER PRIMARY KEY,
    label    TEXT,
    added_at REAL
);
CREATE TABLE IF NOT EXISTS known_users (
    user_id    INTEGER PRIMARY KEY,
    name       TEXT,
    name_lower TEXT
);
CREATE INDEX IF NOT EXISTS idx_known_name ON known_users (name_lower);
CREATE TABLE IF NOT EXISTS stage_ranks (
    driver_id   INTEGER,
    stage_id    INTEGER,
    stage_name  TEXT,
    rank        INTEGER,
    field_size  INTEGER,
    recorded_at REAL
);
CREATE INDEX IF NOT EXISTS idx_stage_ranks ON stage_ranks (driver_id, stage_id);
"""


_INITIALIZED: set[str] = set()


@contextmanager
def _connect(db_path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if db_path not in _INITIALIZED:  # create schema + enable WAL once per file
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            _INITIALIZED.add(db_path)
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_snapshot(db_path: str, snapshot: StatsSnapshot, now: float) -> dict:
    """Persist a completion snapshot, per-stage times and ranks.

    Returns the changes detected versus the previous state (empty on the very
    first run for this driver):
    {new_completions: [...], improvements: [...], rank_changes: [...]}.
    """
    changes: dict = {"new_completions": [], "improvements": [], "rank_changes": []}
    if snapshot.driver_id is None:
        return changes
    driver = snapshot.driver_id
    with _connect(db_path) as conn:
        last_snap = conn.execute(
            "SELECT fetched_at, done_count FROM snapshots "
            "WHERE driver_id=? ORDER BY fetched_at DESC LIMIT 1",
            (driver,),
        ).fetchone()
        first_run = last_snap is None
        # Throttle: only add a completion point when it changed or enough time passed.
        should_record = (
            last_snap is None
            or last_snap["done_count"] != snapshot.done_count
            or now - last_snap["fetched_at"] >= SNAPSHOT_MIN_INTERVAL
        )
        if should_record:
            conn.execute(
                "INSERT INTO snapshots (driver_id, fetched_at, done_count, total) VALUES (?,?,?,?)",
                (driver, now, snapshot.done_count, snapshot.total),
            )
            conn.execute(  # keep a bounded window of history
                "DELETE FROM snapshots WHERE driver_id=? AND rowid NOT IN "
                "(SELECT rowid FROM snapshots WHERE driver_id=? ORDER BY fetched_at DESC LIMIT ?)",
                (driver, driver, MAX_SNAPSHOTS),
            )
        for s in snapshot.stages:
            if not s.done or s.stage_id is None or not s.reference_time:
                continue
            row = conn.execute(
                "SELECT reference_time FROM stage_times "
                "WHERE driver_id=? AND stage_id=? ORDER BY recorded_at DESC LIMIT 1",
                (driver, s.stage_id),
            ).fetchone()
            last = row["reference_time"] if row else None
            if last != s.reference_time:
                if last is None and not first_run:
                    changes["new_completions"].append(
                        {"stage_name": s.name, "time": s.reference_time}
                    )
                elif last is not None:
                    changes["improvements"].append(
                        {"stage_name": s.name, "old": last, "new": s.reference_time}
                    )
                conn.execute(
                    "INSERT INTO stage_times "
                    "(driver_id, stage_id, stage_name, reference_time, seconds, recorded_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        driver,
                        s.stage_id,
                        s.name,
                        s.reference_time,
                        time_to_seconds(s.reference_time),
                        now,
                    ),
                )
            # Rank tracking (only when a rank was resolved this run).
            if s.my_rank is not None:
                rrow = conn.execute(
                    "SELECT rank FROM stage_ranks "
                    "WHERE driver_id=? AND stage_id=? ORDER BY recorded_at DESC LIMIT 1",
                    (driver, s.stage_id),
                ).fetchone()
                last_rank = rrow["rank"] if rrow else None
                if last_rank != s.my_rank:
                    if last_rank is not None and not first_run:
                        changes["rank_changes"].append(
                            {"stage_name": s.name, "old": last_rank, "new": s.my_rank}
                        )
                    conn.execute(
                        "INSERT INTO stage_ranks "
                        "(driver_id, stage_id, stage_name, rank, field_size, recorded_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (driver, s.stage_id, s.name, s.my_rank, s.field_size, now),
                    )
    return changes


def completion_history(db_path: str, driver_id: int, limit: int = 60) -> list[dict]:
    """Return recent completion snapshots (oldest first) for a driver."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT fetched_at, done_count, total FROM snapshots "
            "WHERE driver_id=? ORDER BY fetched_at DESC LIMIT ?",
            (driver_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def recent_improvements(db_path: str, driver_id: int, limit: int = 10) -> list[dict]:
    """Stages whose time improved over history, most recent change first."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT stage_id, stage_name,
                   COUNT(*) AS n,
                   MIN(seconds) AS best_seconds,
                   MAX(recorded_at) AS last_change
            FROM stage_times WHERE driver_id=?
            GROUP BY stage_id HAVING n > 1
            ORDER BY last_change DESC LIMIT ?
            """,
            (driver_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def rank_movers(db_path: str, driver_id: int, limit: int = 10) -> list[dict]:
    """Stages whose rank changed over history: {stage_name, first, last, delta}.

    delta = last - first (negative = climbed up). Sorted by biggest move first.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT stage_id, stage_name, COUNT(*) AS n,
                   (SELECT rank FROM stage_ranks r2 WHERE r2.driver_id=r.driver_id
                    AND r2.stage_id=r.stage_id ORDER BY recorded_at ASC LIMIT 1) AS first_rank,
                   (SELECT rank FROM stage_ranks r3 WHERE r3.driver_id=r.driver_id
                    AND r3.stage_id=r.stage_id ORDER BY recorded_at DESC LIMIT 1) AS last_rank
            FROM stage_ranks r WHERE driver_id=?
            GROUP BY stage_id HAVING n > 1
            """,
            (driver_id,),
        ).fetchall()
    movers = [
        {
            "stage_name": row["stage_name"],
            "stage_id": row["stage_id"],
            "first": row["first_rank"],
            "last": row["last_rank"],
            "delta": row["last_rank"] - row["first_rank"],
        }
        for row in rows
        if row["first_rank"] != row["last_rank"]
    ]
    movers.sort(key=lambda m: abs(m["delta"]), reverse=True)
    return movers[:limit]


def list_rivals(db_path: str) -> list[Rival]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT user_id, label FROM rivals ORDER BY added_at").fetchall()
    return [Rival(user_id=r["user_id"], label=r["label"]) for r in rows]


def add_rival(db_path: str, user_id: int, label: str | None, now: float) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO rivals (user_id, label, added_at) VALUES (?,?,?)",
            (user_id, label, now),
        )


def remove_rival(db_path: str, user_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM rivals WHERE user_id=?", (user_id,))


def remember_users(db_path: str, pairs: list[tuple[int, str]]) -> None:
    """Record (user_id, name) pairs seen in leaderboards for later username lookup."""
    rows = [(uid, name, name.lower()) for uid, name in pairs if uid and name]
    if not rows:
        return
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO known_users (user_id, name, name_lower) VALUES (?,?,?)",
            rows,
        )


def find_user(db_path: str, name: str) -> tuple[int, str] | None:
    """Resolve a username from previously-seen drivers: exact, then unique substring."""
    key = name.strip().lower()
    if not key:
        return None
    with _connect(db_path) as conn:
        exact = conn.execute(
            "SELECT user_id, name FROM known_users WHERE name_lower=? LIMIT 1", (key,)
        ).fetchone()
        if exact:
            return exact["user_id"], exact["name"]
        like = conn.execute(
            "SELECT user_id, name FROM known_users WHERE name_lower LIKE ? LIMIT 2",
            (f"%{key}%",),
        ).fetchall()
    return (like[0]["user_id"], like[0]["name"]) if len(like) == 1 else None
