"""Scraping and parsing of stage stats from rallysimfans.hu.

Everything comes from a single page:
`hotlap.php?centerbox=hotlap_drvtimes&user_id=<id>`. It contains two tables:

- **Hotlap Stages**: the full stage catalog (columns ID / Stage / Length),
  grouped by country (header rows `tr.fejlec2` with a flag). Each stage row also
  carries a tooltip with the surface (gravel / tarmac / snow).
- **Hotlap Rank**: the driver's times (columns Stage / Car / Stage Time /
  Diff 1st / Uploaded). A stage listed here is *completed*, with its *reference time*.

A catalog stage absent from the Rank table is *not completed*.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

import httpx
from selectolax.parser import HTMLParser

from .config import BASE_URL
from .models import Career, HotlapEntry, Leaderboard, Stage, StatsSnapshot

_USER_ID_RE = re.compile(r"usersstats\.php\?user_stats=(\d+)")
_STAGEID_RE = re.compile(r"stageid=(\d+)")
_TIME_RE = re.compile(r"\d{1,2}:\d{2}[.:]\d{2,3}")
_LENGTH_RE = re.compile(r"([\d.]+)\s*km")
_SURFACE_RE = re.compile(r"Surface:</b></td><td>([^<]+)</td>", re.IGNORECASE)
_AUTHOR_RE = re.compile(r"Author:</b></td><td>([^<]+)</td>", re.IGNORECASE)
_FLAG_RE = re.compile(r"flag/([A-Za-z]{2})\.", re.IGNORECASE)
# Header row of the driver's Rank table: link to their stats page + display name.
# The board owner's link carries a distinctive color style (unlike the ~60 other
# "title=Stats" links in the side widgets).
_DRIVER_RE = re.compile(
    r'usersstats\.php\?user_stats=(\d+)"\s+title="Stats"\s+style="color:#FFFDCD">.*?<b>([^<]+)</b>',
    re.IGNORECASE | re.DOTALL,
)


class ScrapeError(RuntimeError):
    """Scraping/parsing failed (site layout changed?)."""


def get_my_user_id(client: httpx.Client) -> int:
    """Read the logged-in account id from the 'Profile > Stats' menu link."""
    resp = client.get(f"{BASE_URL}/hotlap.php?centerbox=recent")
    resp.raise_for_status()
    match = _USER_ID_RE.search(resp.text)
    if not match:
        raise ScrapeError(
            "Could not determine my user_id ('Stats' link not found). Am I logged in?"
        )
    return int(match.group(1))


def fetch_drvtimes_html(client: httpx.Client, user_id: int) -> str:
    """Download the 'driver times' page (catalog + times) for a user_id."""
    url = f"{BASE_URL}/hotlap.php?centerbox=hotlap_drvtimes&user_id={user_id}"
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def _parse_length(text: str) -> float | None:
    match = _LENGTH_RE.search(text)
    return float(match.group(1)) if match else None


def _parse_driver(tree_html: str) -> tuple[int | None, str | None]:
    """Extract the board owner's (user_id, display name) from the Rank header."""
    match = _DRIVER_RE.search(tree_html)
    if not match:
        return None, None
    return int(match.group(1)), match.group(2).strip()


def _parse_catalog(tree: HTMLParser) -> list[Stage]:
    """Parse the 'Hotlap Stages' catalog (all stages), grouped by country."""
    stages: list[Stage] = []
    country: str | None = None
    country_code: str | None = None
    for tr in tree.css("tr"):
        classes = tr.attributes.get("class") or ""
        # Country header: a fejlec2 row containing a flag image.
        if "fejlec2" in classes:
            flag = tr.css_first("img[src*='flag']")
            label = tr.css_first("b")
            if flag is not None and label is not None:
                country = label.text(strip=True)
                m = _FLAG_RE.search(flag.attributes.get("src", ""))
                country_code = m.group(1).upper() if m else None
            continue
        tds = tr.css("td")
        if len(tds) == 3 and tr.css_first("a[href*='rsfhotlap']") is not None:
            sid = tds[0].text(strip=True)
            row_html = tr.html or ""
            surface = _SURFACE_RE.search(row_html)
            author = _AUTHOR_RE.search(row_html)
            stages.append(
                Stage(
                    stage_id=int(sid) if sid.isdigit() else None,
                    name=tds[1].text(strip=True),
                    country=country,
                    country_code=country_code,
                    surface=surface.group(1).strip().lower() if surface else None,
                    author=author.group(1).strip() if author else None,
                    length_km=_parse_length(tds[2].text(strip=True)),
                )
            )
    return stages


def _parse_done(tree: HTMLParser) -> dict[int, dict[str, str]]:
    """Parse the 'Hotlap Rank' table: times keyed by stage_id.

    Returns {stage_id: {time, car, diff_first, uploaded}}. A row is recognized as
    a time if it has at least 5 cells and the 3rd looks like a chrono (mm:ss.xxx).
    """
    done: dict[int, dict[str, str]] = {}
    for tr in tree.css("tr"):
        tds = tr.css("td")
        if len(tds) < 5:
            continue
        stage_time = tds[2].text(strip=True)
        if not _TIME_RE.fullmatch(stage_time):
            continue
        link = tds[0].css_first("a[href*='stageid=']")
        if link is None:
            continue
        m = _STAGEID_RE.search(link.attributes.get("href", ""))
        if not m:
            continue
        done[int(m.group(1))] = {
            "time": stage_time,
            "car": tds[1].text(strip=True),
            "diff_first": tds[3].text(strip=True),
            "uploaded": tds[4].text(strip=True),
        }
    return done


def fetch_stage_html(client: httpx.Client, stage_id: int) -> str:
    """Download a stage's hotlap leaderboard page."""
    url = f"{BASE_URL}/hotlap.php?centerbox=rsfhotlap&stageid={stage_id}"
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def _parse_driver_cell(td) -> tuple[str, int | None]:
    """Extract (driver name, user_id) from a leaderboard driver cell."""
    link = td.css_first("a[href*='hotlap_drvtimes']")
    if link is None:
        return td.text(strip=True), None
    href = link.attributes.get("href", "")
    uid_match = re.search(r"user_id=(\d+)", href)
    name_match = re.search(r"username=([^&\"]+)", href)
    name = unquote(name_match.group(1)).strip() if name_match else td.text(strip=True)
    return name, int(uid_match.group(1)) if uid_match else None


def parse_leaderboard(html: str, stage_id: int) -> Leaderboard:
    """Parse a stage's full hotlap leaderboard.

    Columns are: Pos, Driver, Car, <checkpoints...>, Finish Time, Diff. Prev,
    Diff. First, Uploaded. The number of checkpoints varies per stage, so the
    fixed head (Pos/Driver/Car) and tail (Finish/DiffPrev/DiffFirst/Uploaded)
    are anchored and everything in between is treated as checkpoints.
    """
    tree = HTMLParser(html)
    entries: list[HotlapEntry] = []
    for tr in tree.css("tr.paros, tr.paratlan"):
        tds = tr.css("td")
        if len(tds) < 7:
            continue
        pos_text = tds[0].text(strip=True)
        if not pos_text.isdigit() or tr.css_first("a[href*='hotlap_drvtimes']") is None:
            continue
        driver, driver_id = _parse_driver_cell(tds[1])
        entries.append(
            HotlapEntry(
                position=int(pos_text),
                driver=driver,
                driver_id=driver_id,
                car=tds[2].text(strip=True),
                checkpoints=[c.text(strip=True) for c in tds[3:-4]],
                finish_time=tds[-4].text(strip=True),
                diff_prev=tds[-3].text(strip=True),
                diff_first=tds[-2].text(strip=True),
                uploaded=tds[-1].text(strip=True),
            )
        )
    # Stage metadata from the catalog present on the same page.
    stage = next((s for s in _parse_catalog(tree) if s.stage_id == stage_id), None)
    return Leaderboard(stage_id=stage_id, stage=stage, entries=entries)


_DRV_LINK_RE = re.compile(r"hotlap_drvtimes&user_id=(\d+)&username=([^\"&]+)")


def build_user_index(html: str) -> dict[str, tuple[int, str]]:
    """Map lowercased driver name -> (user_id, display name) from drvtimes links."""
    index: dict[str, tuple[int, str]] = {}
    for m in _DRV_LINK_RE.finditer(html):
        name = unquote(m.group(2)).strip()
        if name:
            index[name.lower()] = (int(m.group(1)), name)
    return index


def fetch_recent_html(client: httpx.Client) -> str:
    """Download the 'recent hotlaps' page (rich source of user_id/username pairs)."""
    resp = client.get(f"{BASE_URL}/hotlap.php?centerbox=recent")
    resp.raise_for_status()
    return resp.text


def fetch_usersstats_html(client: httpx.Client, user_id: int) -> str:
    """Download a driver's aggregate stats page."""
    resp = client.get(f"{BASE_URL}/usersstats.php?user_stats={user_id}")
    resp.raise_for_status()
    return resp.text


def _to_int(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def parse_career(html: str) -> Career:
    """Parse aggregate figures (rallies, finish rate, km) from a stats page."""
    tree = HTMLParser(html)
    career = Career()
    for tr in tree.css("tr.fejlec, tr.fejlec2"):
        cells = [c.text(strip=True) for c in tr.css("td")]
        if not cells:
            continue
        label = cells[0].lower()
        value = cells[-1] if len(cells) > 1 else ""
        if "entered rall" in label:
            career.entered_rallies = _to_int(value)
        elif "finished rall" in label:
            count = re.match(r"[\d,]+", value)  # number before the "(x%)" part
            career.finished_rallies = _to_int(count.group(0)) if count else None
            pct = re.search(r"\(([\d.]+)%\)", value)
            career.finish_pct = float(pct.group(1)) if pct else None
        elif "kilomet" in label or "covered" in label:
            m = re.search(r"([\d,]+)\s*Stage.*?([\d,]+)\s*km", " ".join(cells))
            if m:
                career.stages_driven = _to_int(m.group(1))
                career.km_driven = _to_int(m.group(2))
    return career


def parse_stats(html: str) -> StatsSnapshot:
    """Build the full snapshot of a driver's stages from the drvtimes HTML."""
    tree = HTMLParser(html)
    stages = _parse_catalog(tree)
    if not stages:
        raise ScrapeError("Empty stage catalog: page layout changed, or page not authenticated.")
    done = _parse_done(tree)
    for stage in stages:
        detail = done.get(stage.stage_id) if stage.stage_id is not None else None
        if detail is not None:
            stage.done = True
            stage.reference_time = detail["time"]
            stage.car = detail["car"]
            stage.diff_first = detail["diff_first"]
            stage.uploaded = detail["uploaded"]
    driver_id, driver_name = _parse_driver(html)
    return StatsSnapshot(driver_id=driver_id, driver_name=driver_name, stages=stages)
