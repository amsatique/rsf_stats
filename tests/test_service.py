"""Tests for load-reduction behaviour (cooldown, stale-serving, lazy fetches)."""

from __future__ import annotations

import time

import pytest

from rsf_stats import service
from rsf_stats.config import Settings
from rsf_stats.models import StatsSnapshot
from rsf_stats.service import RateLimited


def _settings(tmp_path) -> Settings:
    return Settings(username="u", password="p", db_path=str(tmp_path / "t.db"))


def test_note_rate_limit_uses_retry_after():
    service.clear_cache()
    now = 1000.0
    service._note_rate_limit(type("R", (), {"headers": {"Retry-After": "42"}})(), now)
    assert service._in_cooldown(now + 41)
    assert not service._in_cooldown(now + 43)
    service.clear_cache()


def test_cooldown_serves_stale_without_login(tmp_path, monkeypatch):
    service.clear_cache()
    stale = StatsSnapshot(driver_id=1, driver_name="Me", stages=[], fetched_at=0.0)
    service._CACHE[None] = stale
    service._COOLDOWN_UNTIL = time.time() + 300

    def boom(*a, **k):
        raise AssertionError("must not contact the server while rate-limited")

    monkeypatch.setattr(service, "login", boom)
    out = service.get_stats(_settings(tmp_path))
    assert out is stale  # served from cache, no network
    service.clear_cache()


def test_cooldown_raises_when_no_cache(tmp_path, monkeypatch):
    service.clear_cache()
    service._COOLDOWN_UNTIL = time.time() + 300
    monkeypatch.setattr(service, "login", lambda *a, **k: pytest.fail("no login expected"))
    with pytest.raises(RateLimited):
        service.get_stats(_settings(tmp_path))
    service.clear_cache()
