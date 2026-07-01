"""Data models for stage statistics."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from pydantic import BaseModel, computed_field

from .config import BASE_URL


def flag_emoji(country_code: str | None) -> str:
    """Turn a 2-letter ISO country code into a flag emoji ('AR' -> '🇦🇷')."""
    if not country_code or len(country_code) != 2 or not country_code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in country_code.upper())


def time_to_seconds(value: str | None) -> float | None:
    """Parse a chrono ('4:55.920', '1:04.685', '12.189') into seconds."""
    if not value:
        return None
    try:
        seconds = 0.0
        for part in value.replace(",", ".").split(":"):
            seconds = seconds * 60 + float(part)
        return seconds
    except ValueError:
        return None


def seconds_to_str(seconds: float | None) -> str | None:
    """Format seconds back into a chrono string ('1:08.034', '15.697')."""
    if seconds is None:
        return None
    minutes = int(seconds // 60)
    rem = seconds - 60 * minutes
    return f"{minutes}:{rem:06.3f}" if minutes else f"{rem:.3f}"


class Stage(BaseModel):
    """Personal statistics for a single stage."""

    stage_id: int | None = None
    name: str
    country: str | None = None
    country_code: str | None = None
    surface: str | None = None  # gravel / tarmac / snow
    author: str | None = None
    length_km: float | None = None
    done: bool = False
    reference_time: str | None = None  # my time, e.g. "03:12.456"
    car: str | None = None  # car used for that time
    diff_first: str | None = None  # gap to the world record
    uploaded: str | None = None  # upload timestamp
    my_rank: int | None = None  # my position in the stage leaderboard
    field_size: int | None = None  # total drivers ranked on this stage
    rank_estimated: bool = False  # True if my_rank is inferred (time not on public board)
    gain_potential: float | None = None  # seconds I'd save by matching best sectors

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str | None:
        """Link to the stage's hotlap page on rallysimfans.hu."""
        if self.stage_id is None:
            return None
        return f"{BASE_URL}/hotlap.php?centerbox=rsfhotlap&stageid={self.stage_id}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def flag(self) -> str:
        return flag_emoji(self.country_code)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def image_url(self) -> str | None:
        """Public preview image of the stage."""
        if self.stage_id is None:
            return None
        return f"{BASE_URL}/images/stages/{self.stage_id}.jpg"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def percentile(self) -> float | None:
        """Top-% among the field (lower is better). None if unranked."""
        if self.my_rank is None or not self.field_size:
            return None
        return round(100 * self.my_rank / self.field_size, 1)


class CountryStat(BaseModel):
    """Completion summary for one country."""

    country: str
    country_code: str | None = None
    total: int
    done: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def flag(self) -> str:
        return flag_emoji(self.country_code)

    @property
    def remaining(self) -> int:
        return self.total - self.done


class SurfaceStat(BaseModel):
    """Completion summary for one surface type."""

    surface: str
    total: int
    done: int
    km_total: float = 0.0
    km_done: float = 0.0


class StrengthStat(BaseModel):
    """Average finishing percentile over ranked stages of one group."""

    label: str
    country_code: str | None = None
    stages: int
    avg_percentile: float  # lower is better (top-%)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def flag(self) -> str:
        return flag_emoji(self.country_code)


class Career(BaseModel):
    """Aggregate career figures from the user's stats page."""

    entered_rallies: int | None = None
    finished_rallies: int | None = None
    finish_pct: float | None = None
    stages_driven: int | None = None
    km_driven: int | None = None


class HotlapEntry(BaseModel):
    """One recorded hotlap in a stage's leaderboard."""

    position: int | None = None
    driver: str
    driver_id: int | None = None
    car: str | None = None
    checkpoints: list[str] = []
    finish_time: str | None = None
    diff_prev: str | None = None
    diff_first: str | None = None
    uploaded: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sectors(self) -> list[float]:
        """Per-sector times (seconds), derived from cumulative checkpoints + finish."""
        cum = [time_to_seconds(c) for c in self.checkpoints]
        cum.append(time_to_seconds(self.finish_time))
        if any(c is None for c in cum) or not cum:
            return []
        out = [cum[0]]
        out += [cum[i] - cum[i - 1] for i in range(1, len(cum))]
        return [round(x, 3) for x in out]


class SectorAnalysis(BaseModel):
    """Fastest sector times across the field and the resulting ideal lap."""

    count: int
    best_seconds: list[float | None]
    best_driver: list[str | None]
    ideal_seconds: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def best_str(self) -> list[str | None]:
        return [seconds_to_str(s) for s in self.best_seconds]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ideal_str(self) -> str | None:
        return seconds_to_str(self.ideal_seconds)


class Leaderboard(BaseModel):
    """All recorded hotlaps for a single stage."""

    stage_id: int
    stage: Stage | None = None  # catalog metadata (name, country, surface, length)
    entries: list[HotlapEntry]
    fetched_at: float = 0.0

    @property
    def count(self) -> int:
        return len(self.entries)

    def find_rank(self, driver_id: int) -> int | None:
        """Position of a given driver in this leaderboard, if present."""
        for e in self.entries:
            if e.driver_id == driver_id:
                return e.position
        return None

    def entry_for(self, driver_id: int) -> HotlapEntry | None:
        for e in self.entries:
            if e.driver_id == driver_id:
                return e
        return None

    def car_breakdown(self, top: int = 8) -> list[tuple[str, int]]:
        """Most-used cars in the leaderboard (car, count), most common first."""
        counter = Counter(e.car for e in self.entries if e.car)
        return counter.most_common(top)

    def sector_analysis(self) -> SectorAnalysis:
        """Fastest time per sector across the field, and the ideal (theoretical) lap."""
        n = max((len(e.sectors) for e in self.entries), default=0)
        best_seconds: list[float | None] = []
        best_driver: list[str | None] = []
        for i in range(n):
            candidates = [
                (e.sectors[i], e.driver)
                for e in self.entries
                if len(e.sectors) > i and e.sectors[i] > 0
            ]
            if candidates:
                sec, drv = min(candidates, key=lambda x: x[0])
                best_seconds.append(sec)
                best_driver.append(drv)
            else:
                best_seconds.append(None)
                best_driver.append(None)
        ideal = (
            round(sum(s for s in best_seconds if s is not None), 3)
            if best_seconds and all(s is not None for s in best_seconds)
            else None
        )
        return SectorAnalysis(
            count=n, best_seconds=best_seconds, best_driver=best_driver, ideal_seconds=ideal
        )

    def gain_potential(self, driver_id: int) -> float | None:
        """Seconds a driver would save by matching the best sector times."""
        entry = self.entry_for(driver_id)
        if entry is None or not entry.sectors:
            return None
        best = self.sector_analysis().best_seconds
        deficit = 0.0
        for i, mine in enumerate(entry.sectors):
            if i < len(best) and best[i] is not None and mine > best[i]:
                deficit += mine - best[i]
        return round(deficit, 3)

    def sector_ranks(self, driver_id: int) -> list[int]:
        """A driver's position in each sector across the field (1 = fastest)."""
        entry = self.entry_for(driver_id)
        if entry is None or not entry.sectors:
            return []
        ranks = []
        for i, mine in enumerate(entry.sectors):
            better = sum(1 for e in self.entries if len(e.sectors) > i and 0 < e.sectors[i] < mine)
            ranks.append(better + 1)
        return ranks


class Rival(BaseModel):
    """A followed driver."""

    user_id: int
    label: str | None = None


class StatsSnapshot(BaseModel):
    """Snapshot of a driver's stages at a point in time."""

    driver_id: int | None = None
    driver_name: str | None = None
    stages: list[Stage]
    career: Career | None = None
    fetched_at: float = 0.0  # epoch seconds; set by the service layer
    ranks_loaded: bool = False  # whether per-stage ranks have been fetched
    career_loaded: bool = False  # whether the career page has been fetched

    @property
    def total(self) -> int:
        return len(self.stages)

    @property
    def done_count(self) -> int:
        return sum(1 for s in self.stages if s.done)

    def by_country(self) -> list[CountryStat]:
        """Per-country completion, ordered by country name."""
        acc: dict[str, CountryStat] = {}
        for s in self.stages:
            key = s.country or "Unknown"
            stat = acc.get(key)
            if stat is None:
                stat = CountryStat(country=key, country_code=s.country_code, total=0, done=0)
                acc[key] = stat
            stat.total += 1
            if s.done:
                stat.done += 1
        return sorted(acc.values(), key=lambda c: c.country)

    def by_surface(self) -> list[SurfaceStat]:
        """Per-surface completion (+ kilometres), ordered by surface name."""
        acc: dict[str, SurfaceStat] = {}
        for s in self.stages:
            key = s.surface or "unknown"
            stat = acc.get(key)
            if stat is None:
                stat = SurfaceStat(surface=key, total=0, done=0)
                acc[key] = stat
            stat.total += 1
            length = s.length_km or 0.0
            stat.km_total += length
            if s.done:
                stat.done += 1
                stat.km_done += length
        return sorted(acc.values(), key=lambda s: s.surface)

    def suggestions(self, limit: int = 5) -> dict[str, list]:
        """Cheap, computed recommendations of what to tackle next."""
        todo = [s for s in self.stages if not s.done]
        shortest = sorted(
            (s for s in todo if s.length_km is not None), key=lambda s: s.length_km or 0.0
        )[:limit]
        # Countries closest to completion (at least one done, not fully complete).
        near = [
            c
            for c in self.by_country()
            if c.done > 0 and c.remaining > 0 and c.country != "Unknown"
        ]
        near.sort(key=lambda c: (c.remaining, -c.done))
        return {"shortest": shortest, "near_countries": near[:limit]}

    def strengths(self) -> dict[str, list[StrengthStat]]:
        """Average finishing percentile by surface and by country (ranked stages only).

        Only stages where a rank was resolved contribute. Lower percentile = better.
        """

        def group(key_attr: str, code_attr: str | None) -> list[StrengthStat]:
            buckets: dict[str, list] = {}
            codes: dict[str, str | None] = {}
            for s in self.stages:
                pct = s.percentile
                if pct is None:
                    continue
                key = getattr(s, key_attr) or "unknown"
                buckets.setdefault(key, []).append(pct)
                if code_attr:
                    codes[key] = getattr(s, code_attr)
            stats = [
                StrengthStat(
                    label=k,
                    country_code=codes.get(k),
                    stages=len(v),
                    avg_percentile=round(sum(v) / len(v), 1),
                )
                for k, v in buckets.items()
            ]
            return sorted(stats, key=lambda x: x.avg_percentile)

        return {
            "by_surface": group("surface", None),
            "by_country": group("country", "country_code"),
        }

    def activity_calendar(self, weeks: int = 26, today: date | None = None) -> dict:
        """GitHub-style day grid of when I set my current times (by upload date)."""
        counts: Counter[str] = Counter()
        for s in self.stages:
            if s.done and s.uploaded:
                counts[s.uploaded[:10]] += 1
        end = today or date.today()
        start = end - timedelta(days=weeks * 7 - 1)
        start -= timedelta(days=start.weekday())  # align to Monday
        days = []
        d = start
        while d <= end:
            iso = d.isoformat()
            days.append({"date": iso, "count": counts.get(iso, 0)})
            d += timedelta(days=1)
        return {"days": days, "max": max((x["count"] for x in days), default=0)}
