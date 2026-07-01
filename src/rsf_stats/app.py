"""FastAPI application: web dashboard for RallySimFans stats."""

from __future__ import annotations

import csv
import io
import time
from pathlib import Path as FilePath
from urllib.parse import quote

from fastapi import FastAPI, Form, Path, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import storage
from .client import LoginError
from .config import get_settings
from .models import StatsSnapshot, time_to_seconds
from .scraper import ScrapeError
from .service import (
    RateLimited,
    cache_status,
    get_leaderboard,
    get_my_id,
    get_stats,
    resolve_username,
)
from .templating import render

app = FastAPI(title="RSF Stats", description="RallySimFans (RBR) stats")
app.mount("/static", StaticFiles(directory=FilePath(__file__).parent / "static"), name="static")


def _error(request: Request, exc: Exception) -> HTMLResponse:
    """Render the error page; a rate-limit yields 503 + Retry-After."""
    if isinstance(exc, RateLimited):
        retry = max(1, cache_status()["cooldown_seconds"])
        resp = render(request, "error.html", {"message": str(exc), "active": None}, status_code=503)
        resp.headers["Retry-After"] = str(retry)
        return resp
    return render(request, "error.html", {"message": str(exc), "active": None}, status_code=502)


def _nav(snapshot: StatsSnapshot, user_id: int | None, active: str) -> dict:
    """Common context consumed by the shared navigation bar."""
    return {
        "driver_name": snapshot.driver_name,
        "viewing_other": user_id is not None,
        "active": active,
        "snapshot": snapshot,
    }


# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def overview(
    request: Request,
    user_id: int | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> HTMLResponse:
    settings = get_settings()
    try:
        # Overview shows career + progress, but no rank column -> skip the heavy ranks.
        snapshot = get_stats(settings, user_id, force=refresh, with_ranks=False)
    except (LoginError, ScrapeError) as exc:
        return _error(request, exc)

    changes: dict = {}
    history: list[dict] = []
    if user_id is None and snapshot.driver_id is not None:
        changes = storage.record_snapshot(settings.db_path, snapshot, time.time())
        history = storage.completion_history(settings.db_path, snapshot.driver_id)

    return render(
        request,
        "overview.html",
        {
            **_nav(snapshot, user_id, "overview"),
            "total": snapshot.total,
            "done_count": snapshot.done_count,
            "career": snapshot.career,
            "changes": changes,
            "history": history,
            "activity": snapshot.activity_calendar(),
            "suggestions": snapshot.suggestions(),
        },
    )


# --------------------------------------------------------------------------- #
# Stages table
# --------------------------------------------------------------------------- #
@app.get("/stages", response_class=HTMLResponse)
def stages(
    request: Request,
    user_id: int | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> HTMLResponse:
    settings = get_settings()
    try:
        snapshot = get_stats(settings, user_id, force=refresh, with_career=False)
    except (LoginError, ScrapeError) as exc:
        return _error(request, exc)
    return render(
        request,
        "stages.html",
        {
            **_nav(snapshot, user_id, "stages"),
            "stages": snapshot.stages,
            "total": snapshot.total,
            "done_count": snapshot.done_count,
        },
    )


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
@app.get("/analysis", response_class=HTMLResponse)
def analysis(
    request: Request,
    user_id: int | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> HTMLResponse:
    settings = get_settings()
    try:
        snapshot = get_stats(settings, user_id, force=refresh, with_career=False)
    except (LoginError, ScrapeError) as exc:
        return _error(request, exc)

    time_on_table = sorted(
        (s for s in snapshot.stages if s.gain_potential),
        key=lambda s: s.gain_potential or 0,
        reverse=True,
    )
    improvements: list[dict] = []
    movers: list[dict] = []
    if user_id is None and snapshot.driver_id is not None:
        improvements = storage.recent_improvements(settings.db_path, snapshot.driver_id)
        movers = storage.rank_movers(settings.db_path, snapshot.driver_id)

    return render(
        request,
        "analysis.html",
        {
            **_nav(snapshot, user_id, "analysis"),
            "strengths": snapshot.strengths(),
            "time_on_table": time_on_table,
            "improvements": improvements,
            "movers": movers,
            "surfaces": snapshot.by_surface(),
            "countries": snapshot.by_country(),
        },
    )


# --------------------------------------------------------------------------- #
# Compete (rivals + targets + compare form)
# --------------------------------------------------------------------------- #
@app.get("/compete", response_class=HTMLResponse)
def compete(request: Request, notfound: str = Query(default="")) -> HTMLResponse:
    settings = get_settings()
    rival_list = storage.list_rivals(settings.db_path)
    try:
        me = get_stats(settings, with_ranks=False, with_career=False)
    except (LoginError, ScrapeError) as exc:
        return _error(request, exc)

    my = {s.stage_id: (s, time_to_seconds(s.reference_time)) for s in me.stages if s.done}
    me_name = me.driver_name or "Me"
    # driver -> {stage_id: seconds} for the mini-championship.
    driver_times: dict[str, dict[int, float]] = {
        me_name: {sid: sec for sid, (_st, sec) in my.items() if sec is not None}
    }
    summaries = []
    best_targets: dict[int, dict] = {}
    for rival in rival_list:
        try:
            board = get_stats(settings, rival.user_id, with_ranks=False, with_career=False)
        except (LoginError, ScrapeError):
            continue
        shared = my_wins = their_wins = 0
        rival_name = rival.label or board.driver_name or f"user #{rival.user_id}"
        rival_times: dict[int, float] = {}
        for s in board.stages:
            if s.done:
                sec = time_to_seconds(s.reference_time)
                if sec is not None:
                    rival_times[s.stage_id] = sec
            entry = my.get(s.stage_id)
            if entry is None or not s.done:
                continue
            stage, mine = entry
            their = time_to_seconds(s.reference_time)
            if mine is None or their is None:
                continue
            shared += 1
            if mine < their:
                my_wins += 1
            elif their < mine:
                their_wins += 1
                gap = mine - their
                cur = best_targets.get(s.stage_id)
                if cur is None or gap < cur["gap"]:
                    best_targets[s.stage_id] = {
                        "stage": stage,
                        "rival_name": rival_name,
                        "my_time": stage.reference_time,
                        "their_time": s.reference_time,
                        "gap": gap,
                    }
        driver_times[rival_name] = rival_times
        summaries.append(
            {
                "rival": rival,
                "name": board.driver_name or f"user #{rival.user_id}",
                "done": board.done_count,
                "shared": shared,
                "my_wins": my_wins,
                "their_wins": their_wins,
            }
        )
    targets = sorted(best_targets.values(), key=lambda t: t["gap"])
    championship = _championship(driver_times) if len(driver_times) > 1 else []
    return render(
        request,
        "compete.html",
        {
            **_nav(me, None, "compete"),
            "summaries": summaries,
            "targets": targets,
            "championship": championship,
            "notfound": notfound,
        },
    )


def _championship(driver_times: dict[str, dict[int, float]]) -> list[dict]:
    """Points standings across shared stages: 1 point per driver you beat, per stage."""
    names = list(driver_times)
    points = dict.fromkeys(names, 0)
    wins = dict.fromkeys(names, 0)
    contested = dict.fromkeys(names, 0)
    stage_ids = {sid for times in driver_times.values() for sid in times}
    for sid in stage_ids:
        runners = [(n, driver_times[n][sid]) for n in names if sid in driver_times[n]]
        if len(runners) < 2:
            continue
        runners.sort(key=lambda x: x[1])
        for pos, (name, _sec) in enumerate(runners):
            contested[name] += 1
            points[name] += len(runners) - 1 - pos  # drivers beaten on this stage
        wins[runners[0][0]] += 1
    table = [
        {"name": n, "points": points[n], "wins": wins[n], "contested": contested[n]}
        for n in names
        if contested[n] > 0
    ]
    table.sort(key=lambda r: (-r["points"], -r["wins"]))
    return table


@app.get("/compare", response_class=HTMLResponse)
def compare(
    request: Request,
    b: int | None = Query(default=None),
    a: int | None = Query(default=None),
    other: int | None = Query(default=None),
) -> HTMLResponse:
    right_id = b if b is not None else other
    if right_id is None:
        return _error(request, ValueError("Provide a driver to compare against (?b=<user_id>)."))

    settings = get_settings()
    try:
        left = get_stats(settings, a, with_ranks=False, with_career=False)
        right = get_stats(settings, right_id, with_ranks=False, with_career=False)
    except (LoginError, ScrapeError) as exc:
        return _error(request, exc)

    right_by_id = {s.stage_id: s for s in right.stages}
    rows = []
    for s in left.stages:
        t = right_by_id.get(s.stage_id)
        left_sec = time_to_seconds(s.reference_time)
        right_sec = time_to_seconds(t.reference_time) if t else None
        if left_sec is None or right_sec is None:
            continue
        rows.append(
            {
                "stage": s,
                "left_time": s.reference_time,
                "right_time": t.reference_time,
                "delta": left_sec - right_sec,
            }
        )
    rows.sort(key=lambda r: r["delta"])
    return render(
        request,
        "compare.html",
        {**_nav(left, a, "compete"), "rows": rows, "left": left, "right": right},
    )


# Backward-compatible redirects for the folded pages.
@app.get("/rivals")
@app.get("/targets")
def _compete_redirect() -> RedirectResponse:
    return RedirectResponse("/compete", status_code=307)


@app.get("/status", response_class=HTMLResponse)
def status(request: Request) -> HTMLResponse:
    return render(request, "status.html", {"active": None, "status": cache_status()})


# --------------------------------------------------------------------------- #
# Stage detail
# --------------------------------------------------------------------------- #
@app.get("/stage/{stage_id}", response_class=HTMLResponse)
def stage(
    request: Request,
    stage_id: int = Path(..., ge=1),
    refresh: bool = Query(default=False),
) -> HTMLResponse:
    settings = get_settings()
    try:
        board = get_leaderboard(settings, stage_id, force=refresh)
        my_id = get_my_id(settings)
        me = get_stats(settings, with_ranks=False, with_career=False)
    except (LoginError, ScrapeError) as exc:
        return _error(request, exc)

    my_entry = board.entry_for(my_id) if my_id else None
    # If my time isn't in the public leaderboard yet, estimate my position from my
    # own recorded time so the "you" features still show on stages I've completed.
    me_estimate = None
    if my_entry is None:
        mine = next(
            (s for s in me.stages if s.stage_id == stage_id and s.done and s.reference_time),
            None,
        )
        my_sec = time_to_seconds(mine.reference_time) if mine else None
        finishes = sorted(
            f for f in (time_to_seconds(e.finish_time) for e in board.entries) if f is not None
        )
        if my_sec is not None and finishes:
            est = 1 + sum(1 for f in finishes if f < my_sec)
            me_estimate = {
                "position": est,
                "field": len(finishes),
                "time": mine.reference_time,
                "car": mine.car,
                "gap": round(my_sec - finishes[0], 3),
            }
    return render(
        request,
        "stage.html",
        {
            "active": "stages",
            "board": board,
            "my_id": my_id,
            "cars": board.car_breakdown(),
            "sectors": board.sector_analysis(),
            "my_entry": my_entry,
            "sector_ranks": board.sector_ranks(my_id) if my_id else [],
            "me_estimate": me_estimate,
        },
    )


# --------------------------------------------------------------------------- #
# Mutations (rivals)
# --------------------------------------------------------------------------- #
@app.post("/rivals/add")
def rivals_add(identifier: str = Form(...), label: str = Form(default="")) -> RedirectResponse:
    settings = get_settings()
    ident = identifier.strip()
    label = label.strip()
    if ident.isdigit():
        user_id: int | None = int(ident)
    else:
        resolved = resolve_username(settings, ident)
        if resolved is None:
            return RedirectResponse(f"/compete?notfound={quote(ident)}", status_code=303)
        user_id, resolved_name = resolved
        label = label or resolved_name
    storage.add_rival(settings.db_path, user_id, label or None, time.time())
    return RedirectResponse("/compete", status_code=303)


@app.post("/rivals/remove")
def rivals_remove(user_id: int = Form(...)) -> RedirectResponse:
    settings = get_settings()
    storage.remove_rival(settings.db_path, user_id)
    return RedirectResponse("/compete", status_code=303)


# --------------------------------------------------------------------------- #
# JSON / CSV / health
# --------------------------------------------------------------------------- #
@app.get("/api/stats")
def api_stats(user_id: int | None = Query(default=None)) -> JSONResponse:
    settings = get_settings()
    try:
        snapshot = get_stats(settings, user_id)
    except (LoginError, ScrapeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse(snapshot.model_dump())


@app.get("/api/stage/{stage_id}")
def api_stage(stage_id: int = Path(..., ge=1)) -> JSONResponse:
    settings = get_settings()
    try:
        board = get_leaderboard(settings, stage_id)
    except (LoginError, ScrapeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse(board.model_dump())


@app.get("/export.csv")
def export_csv(user_id: int | None = Query(default=None)) -> PlainTextResponse:
    settings = get_settings()
    try:
        snapshot: StatsSnapshot = get_stats(settings, user_id)
    except (LoginError, ScrapeError) as exc:
        return PlainTextResponse(str(exc), status_code=502)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "stage_id",
            "name",
            "country",
            "surface",
            "author",
            "length_km",
            "done",
            "reference_time",
            "car",
            "diff_first",
            "uploaded",
            "my_rank",
            "field_size",
        ]
    )
    for s in snapshot.stages:
        writer.writerow(
            [
                s.stage_id,
                s.name,
                s.country,
                s.surface,
                s.author,
                s.length_km,
                s.done,
                s.reference_time,
                s.car,
                s.diff_first,
                s.uploaded,
                s.my_rank,
                s.field_size,
            ]
        )
    name = snapshot.driver_name or "stats"
    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rsf_{name}.csv"'},
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    """CLI entry point (`rsf-stats`): start the uvicorn server."""
    import uvicorn

    from .log import logger, setup_logging

    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("starting RSF Stats on %s:%s", settings.host, settings.port)
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
