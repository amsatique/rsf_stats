"""Tests for the SQLite persistence layer (history, PBs, rivals)."""

from __future__ import annotations

from rsf_stats import storage
from rsf_stats.models import Stage, StatsSnapshot


def _snapshot(time_346: str, rank_346: int | None = None) -> StatsSnapshot:
    return StatsSnapshot(
        driver_id=42,
        driver_name="Tester",
        stages=[
            Stage(
                stage_id=346,
                name="Fernet Branca",
                done=True,
                reference_time=time_346,
                my_rank=rank_346,
            ),
            Stage(stage_id=376, name="Otra Etapa", done=False),
        ],
    )


def test_history_and_improvement_tracking(tmp_path):
    db = str(tmp_path / "t.db")
    # Timestamps spaced beyond SNAPSHOT_MIN_INTERVAL so each visit is recorded.
    t0, t1, t2 = 0.0, 4000.0, 8000.0
    # First visit: baseline, nothing reported as "changed".
    c = storage.record_snapshot(db, _snapshot("03:12.456"), now=t0)
    assert c["improvements"] == [] and c["new_completions"] == []
    # Second visit: same time, no change recorded.
    c = storage.record_snapshot(db, _snapshot("03:12.456"), now=t1)
    assert c["improvements"] == []
    # Third visit: faster time -> improvement detected.
    c = storage.record_snapshot(db, _snapshot("03:10.000"), now=t2)
    assert len(c["improvements"]) == 1
    assert c["improvements"][0]["old"] == "03:12.456"
    assert c["improvements"][0]["new"] == "03:10.000"

    history = storage.completion_history(db, 42)
    assert len(history) == 3
    assert history[0]["done_count"] == 1

    recent = storage.recent_improvements(db, 42)
    assert len(recent) == 1
    assert recent[0]["stage_id"] == 346
    assert recent[0]["n"] == 2  # two distinct recorded times


def test_snapshot_throttled_when_unchanged(tmp_path):
    db = str(tmp_path / "t.db")
    for now in (0.0, 10.0, 20.0):  # same done_count, within the interval
        storage.record_snapshot(db, _snapshot("03:12.456"), now=now)
    assert len(storage.completion_history(db, 42)) == 1  # only the baseline recorded


def test_rank_change_tracking(tmp_path):
    db = str(tmp_path / "t.db")
    storage.record_snapshot(db, _snapshot("03:12.456", rank_346=100), now=1.0)  # baseline
    c = storage.record_snapshot(db, _snapshot("03:12.456", rank_346=100), now=2.0)
    assert c["rank_changes"] == []  # unchanged
    c = storage.record_snapshot(db, _snapshot("03:12.456", rank_346=90), now=3.0)
    assert len(c["rank_changes"]) == 1
    assert c["rank_changes"][0]["old"] == 100
    assert c["rank_changes"][0]["new"] == 90


def test_rank_movers(tmp_path):
    db = str(tmp_path / "t.db")
    storage.record_snapshot(db, _snapshot("03:12.456", rank_346=100), now=1.0)
    storage.record_snapshot(db, _snapshot("03:12.456", rank_346=100), now=2.0)
    storage.record_snapshot(db, _snapshot("03:12.456", rank_346=80), now=3.0)
    movers = storage.rank_movers(db, 42)
    assert len(movers) == 1
    assert movers[0]["first"] == 100
    assert movers[0]["last"] == 80
    assert movers[0]["delta"] == -20  # climbed 20 places


def test_known_users_resolution(tmp_path):
    db = str(tmp_path / "t.db")
    storage.remember_users(db, [(14447, "Tommi Hallman"), (17093, "Raoul Dahlqvist")])
    # exact, case-insensitive
    assert storage.find_user(db, "tommi hallman") == (14447, "Tommi Hallman")
    # unique substring
    assert storage.find_user(db, "Raoul") == (17093, "Raoul Dahlqvist")
    # unknown
    assert storage.find_user(db, "Nobody") is None
    # ambiguous substring -> no guess
    storage.remember_users(db, [(1, "Ana One"), (2, "Ana Two")])
    assert storage.find_user(db, "Ana") is None


def test_rivals_crud(tmp_path):
    db = str(tmp_path / "t.db")
    assert storage.list_rivals(db) == []
    storage.add_rival(db, 17093, "Raoul", now=1.0)
    storage.add_rival(db, 14447, None, now=2.0)
    rivals = storage.list_rivals(db)
    assert [r.user_id for r in rivals] == [17093, 14447]
    assert rivals[0].label == "Raoul"
    storage.remove_rival(db, 17093)
    assert [r.user_id for r in storage.list_rivals(db)] == [14447]
