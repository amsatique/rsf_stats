"""Orchestration: login -> scraping -> stats, with caching and server-friendly limits.

Load-reduction measures:
- a single authenticated session is reused across requests (re-login only on expiry);
- stage leaderboards are cached far longer than the personal board (they change slowly);
- on HTTP 429 we honour Retry-After, enter a cooldown and serve stale cache instead
  of hammering the server;
- career and per-stage ranks are fetched lazily, only for the pages that show them.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

import httpx

from . import storage
from .client import login
from .config import Settings
from .log import logger
from .models import Leaderboard, StatsSnapshot, time_to_seconds
from .scraper import (
    ScrapeError,
    build_user_index,
    fetch_drvtimes_html,
    fetch_recent_html,
    fetch_stage_html,
    fetch_usersstats_html,
    get_my_user_id,
    parse_career,
    parse_leaderboard,
    parse_stats,
)

# Max stage leaderboards fetched per board load to compute ranks (protects the server).
RANK_MAX_FETCHES = 30

_CACHE: dict[int | None, StatsSnapshot] = {}
_LEADERBOARD_CACHE: dict[int, Leaderboard] = {}
_SESSION: httpx.Client | None = None
_COOLDOWN_UNTIL = 0.0  # epoch; while now < this, we avoid the server entirely
# Single-flight: the module state above is process-global, so the app MUST run with
# a single worker. This lock serializes cache-miss scrapes to avoid duplicate hits.
_LOCK = threading.Lock()


class RateLimited(ScrapeError):
    """The server is rate-limiting us; back off and try later."""


def clear_cache() -> None:
    global _SESSION, _COOLDOWN_UNTIL
    _CACHE.clear()
    _LEADERBOARD_CACHE.clear()
    _COOLDOWN_UNTIL = 0.0
    if _SESSION is not None:
        with contextlib.suppress(Exception):
            _SESSION.close()
    _SESSION = None


# --------------------------------------------------------------------------- #
# Session reuse + rate-limit handling
# --------------------------------------------------------------------------- #
def _session(settings: Settings) -> httpx.Client:
    global _SESSION
    if _SESSION is None or _SESSION.is_closed:
        _SESSION = login(settings)
    else:
        logger.debug("session: reusing authenticated session")
    return _SESSION


def _reset_session() -> None:
    global _SESSION
    if _SESSION is not None:
        with contextlib.suppress(Exception):
            _SESSION.close()
    _SESSION = None


def _with_session(settings: Settings, op: Callable[[httpx.Client], object]) -> object:
    """Run ``op`` with the shared session; re-login once if the session expired.

    A 429 is NOT retried here — it is not an auth problem and is handled by the
    caller (cooldown + stale cache).
    """
    try:
        return op(_session(settings))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise
        _reset_session()
        return op(_session(settings))
    except ScrapeError:
        # Likely a logged-out page served with 200 -> refresh the session once.
        _reset_session()
        return op(_session(settings))


def _in_cooldown(now: float) -> bool:
    return now < _COOLDOWN_UNTIL


def _note_rate_limit(resp: httpx.Response, now: float) -> None:
    global _COOLDOWN_UNTIL
    retry = (resp.headers.get("Retry-After") or "").strip()
    delay = float(retry) if retry.isdigit() else 60.0
    _COOLDOWN_UNTIL = max(_COOLDOWN_UNTIL, now + delay)
    logger.warning("rate-limited (429): backing off for %.0fs", delay)


# --------------------------------------------------------------------------- #
# Leaderboards
# --------------------------------------------------------------------------- #
def _leaderboard(
    client: httpx.Client, stage_id: int, now: float, ttl: float, *, force: bool, db_path: str | None
) -> Leaderboard:
    cached = _LEADERBOARD_CACHE.get(stage_id)
    if not force and cached is not None and now - cached.fetched_at < ttl:
        return cached
    board = parse_leaderboard(fetch_stage_html(client, stage_id), stage_id)
    board.fetched_at = now
    _LEADERBOARD_CACHE[stage_id] = board
    if db_path:
        storage.remember_users(
            db_path, [(e.driver_id, e.driver) for e in board.entries if e.driver_id]
        )
    return board


def _enrich_ranks(
    client: httpx.Client,
    snapshot: StatsSnapshot,
    now: float,
    delay: float,
    ttl: float,
    db_path: str,
) -> bool:
    """Fill my_rank / gain_potential for completed stages. Returns True if complete.

    Stops (returning False) on the first network/rate-limit error so we never
    hammer the server; a later visit resumes once the cooldown has passed.
    """
    if snapshot.driver_id is None:
        return True
    done = [s for s in snapshot.stages if s.done and s.stage_id is not None]
    todo = done[:RANK_MAX_FETCHES]
    if todo:
        logger.info(
            "ranks: resolving up to %d stage leaderboards for driver %s",
            len(todo),
            snapshot.driver_id,
        )
    for i, stage in enumerate(todo):
        cached = _LEADERBOARD_CACHE.get(stage.stage_id)
        if delay and i > 0 and (cached is None or now - cached.fetched_at >= ttl):
            time.sleep(delay)
        try:
            board = _leaderboard(client, stage.stage_id, now, ttl, force=False, db_path=db_path)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                _note_rate_limit(exc.response, now)
            return False
        except httpx.HTTPError:
            return False
        stage.field_size = board.count
        real = board.find_rank(snapshot.driver_id)
        if real is not None:
            stage.my_rank = real
        else:
            # Not on the public board yet: estimate the rank from my own time.
            my_sec = time_to_seconds(stage.reference_time)
            if my_sec is not None:
                finishes = [
                    f
                    for f in (time_to_seconds(e.finish_time) for e in board.entries)
                    if f is not None
                ]
                if finishes:
                    stage.my_rank = 1 + sum(1 for f in finishes if f < my_sec)
                    stage.rank_estimated = True
        stage.gain_potential = board.gain_potential(snapshot.driver_id)
    return True


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def get_stats(
    settings: Settings,
    user_id: int | None = None,
    *,
    force: bool = False,
    with_ranks: bool = True,
    with_career: bool = True,
) -> StatsSnapshot:
    """Return a driver's snapshot; career and ranks are fetched only if requested.

    Uses the shared session, the configured cache TTL, and honours the 429
    cooldown (serving stale data rather than re-scraping while rate-limited).
    """

    def _needs(cached: StatsSnapshot | None, now: float) -> tuple[bool, bool, bool]:
        fresh = cached is not None and not force and now - cached.fetched_at < settings.cache_ttl
        build = not fresh
        career = with_career and (build or (cached is not None and not cached.career_loaded))
        ranks = with_ranks and (build or (cached is not None and not cached.ranks_loaded))
        return build, career, ranks

    now = time.time()
    cached = _CACHE.get(user_id)
    if not any(_needs(cached, now)):
        logger.debug("stats[%s]: cache hit", user_id)
        return cached  # fully served from cache — fast path, no lock

    # Single-flight: serialize misses so concurrent requests don't double-scrape.
    with _LOCK:
        now = time.time()
        cached = _CACHE.get(user_id)
        need_build, need_career, need_ranks = _needs(cached, now)
        if not (need_build or need_career or need_ranks):
            return cached  # another request populated it while we waited

        if _in_cooldown(now):
            if cached is not None:
                logger.info("stats[%s]: rate-limited, serving stale cache", user_id)
                return cached
            raise RateLimited("RallySimFans is rate-limiting requests; please retry shortly.")

        logger.info(
            "stats[%s]: %s (career=%s, ranks=%s)",
            user_id,
            "building" if need_build else "top-up",
            need_career,
            need_ranks,
        )

        def op(client: httpx.Client) -> StatsSnapshot:
            snap = cached
            if need_build or snap is None:
                target = user_id if user_id is not None else get_my_user_id(client)
                snap = parse_stats(fetch_drvtimes_html(client, target))
                snap.fetched_at = now
            tid = snap.driver_id if snap.driver_id is not None else (user_id or 0)
            if with_career and not snap.career_loaded:
                try:
                    snap.career = parse_career(fetch_usersstats_html(client, tid))
                    snap.career_loaded = True
                except httpx.HTTPError as exc:
                    r = getattr(exc, "response", None)
                    if r is not None and r.status_code == 429:
                        _note_rate_limit(r, now)  # retry career on a later visit
                    else:
                        snap.career = None
                        snap.career_loaded = True
            if with_ranks and not snap.ranks_loaded:
                snap.ranks_loaded = _enrich_ranks(
                    client,
                    snap,
                    now,
                    settings.request_delay,
                    settings.leaderboard_ttl,
                    settings.db_path,
                )
            return snap

        try:
            snapshot = _with_session(settings, op)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                _note_rate_limit(exc.response, now)
                if cached is not None:
                    return cached
                raise RateLimited("RallySimFans is rate-limiting requests; retry shortly.") from exc
            raise

        _CACHE[user_id] = snapshot
        if user_id is None and snapshot.driver_id is not None:
            _CACHE[snapshot.driver_id] = snapshot
        return snapshot


def get_my_id(settings: Settings) -> int:
    """Return the logged-in account's user_id (reuses cache/session)."""
    cached = _CACHE.get(None)
    if cached is not None and cached.driver_id is not None:
        return cached.driver_id
    return _with_session(settings, get_my_user_id)  # type: ignore[return-value]


def resolve_username(settings: Settings, name: str) -> tuple[int, str] | None:
    """Best-effort username -> (user_id, display name) resolution."""
    key = name.strip().lower()
    if not key:
        return None
    for board in _LEADERBOARD_CACHE.values():
        for e in board.entries:
            if e.driver_id is not None and e.driver and e.driver.lower() == key:
                return e.driver_id, e.driver
    hit = storage.find_user(settings.db_path, name)
    if hit is not None:
        return hit
    if _in_cooldown(time.time()):
        return None
    index = _with_session(settings, lambda c: build_user_index(fetch_recent_html(c)))
    storage.remember_users(settings.db_path, list(index.values()))  # type: ignore[union-attr]
    if key in index:  # type: ignore[operator]
        return index[key]  # type: ignore[index]
    matches = [v for k, v in index.items() if key in k]  # type: ignore[union-attr]
    return matches[0] if len(matches) == 1 else None


def get_leaderboard(settings: Settings, stage_id: int, *, force: bool = False) -> Leaderboard:
    """Return a stage's full hotlap leaderboard (long TTL, 429-aware)."""
    now = time.time()
    cached = _LEADERBOARD_CACHE.get(stage_id)
    if not force and cached is not None and now - cached.fetched_at < settings.leaderboard_ttl:
        return cached  # fast path, no lock

    with _LOCK:
        now = time.time()
        cached = _LEADERBOARD_CACHE.get(stage_id)
        if not force and cached is not None and now - cached.fetched_at < settings.leaderboard_ttl:
            return cached  # populated while we waited
        if _in_cooldown(now):
            if cached is not None:
                return cached
            raise RateLimited("RallySimFans is rate-limiting requests; please retry shortly.")

        def op(client: httpx.Client) -> Leaderboard:
            return _leaderboard(
                client,
                stage_id,
                now,
                settings.leaderboard_ttl,
                force=force,
                db_path=settings.db_path,
            )

        try:
            return _with_session(settings, op)  # type: ignore[return-value]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                _note_rate_limit(exc.response, now)
                if cached is not None:
                    return cached
                raise RateLimited("RallySimFans is rate-limiting requests; retry shortly.") from exc
            raise


def cache_status() -> dict:
    """Snapshot of the in-memory caches and rate-limit state (for /status)."""
    now = time.time()
    return {
        "session_open": _SESSION is not None and not _SESSION.is_closed,
        "cooldown_active": _in_cooldown(now),
        "cooldown_seconds": max(0, int(_COOLDOWN_UNTIL - now)),
        "snapshots_cached": len(_CACHE),
        "leaderboards_cached": len(_LEADERBOARD_CACHE),
    }
