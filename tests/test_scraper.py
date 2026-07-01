"""Tests for stats parsing (synthetic fixture + edge cases)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from rsf_stats.models import flag_emoji, seconds_to_str, time_to_seconds
from rsf_stats.scraper import ScrapeError, parse_career, parse_leaderboard, parse_stats

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = (FIXTURES / "drvtimes_sample.html").read_text(encoding="utf-8")
LEADERBOARD = (FIXTURES / "leaderboard_sample.html").read_text(encoding="utf-8")


def test_parse_catalog_lists_all_stages():
    snapshot = parse_stats(FIXTURE)
    assert snapshot.total == 3
    names = {s.name for s in snapshot.stages}
    assert names == {"Fernet Branca 2015", "Otra Etapa", "Some Austrian Stage"}


def test_country_grouping_and_codes():
    snapshot = parse_stats(FIXTURE)
    by_name = {s.name: s for s in snapshot.stages}
    assert by_name["Fernet Branca 2015"].country == "Argentina"
    assert by_name["Fernet Branca 2015"].country_code == "AR"
    assert by_name["Some Austrian Stage"].country == "Austria"
    assert by_name["Some Austrian Stage"].country_code == "AT"


def test_surface_parsed():
    by_name = {s.name: s for s in parse_stats(FIXTURE).stages}
    assert by_name["Fernet Branca 2015"].surface == "gravel"
    assert by_name["Otra Etapa"].surface == "tarmac"
    assert by_name["Some Austrian Stage"].surface == "snow"


def test_length_parsed():
    by_name = {s.name: s for s in parse_stats(FIXTURE).stages}
    assert by_name["Fernet Branca 2015"].length_km == 6.0
    assert by_name["Otra Etapa"].length_km == 12.3


def test_done_details():
    by_id = {s.stage_id: s for s in parse_stats(FIXTURE).stages}
    # 346 and 101 have a time in the Rank table -> completed with full details
    assert by_id[346].done is True
    assert by_id[346].reference_time == "03:12.456"
    assert by_id[346].car == "Peugeot 208"
    assert by_id[346].diff_first == "1.230"
    assert by_id[346].uploaded == "2026-06-01 10:00:00"
    # 376 absent from Rank -> not completed
    assert by_id[376].done is False
    assert by_id[376].reference_time is None
    assert by_id[376].car is None


def test_driver_header():
    snapshot = parse_stats(FIXTURE)
    assert snapshot.driver_id == 42
    assert snapshot.driver_name == "Test Driver"


def test_counts_and_country_summary():
    snapshot = parse_stats(FIXTURE)
    assert snapshot.done_count == 2
    assert snapshot.total == 3
    by_country = {c.country: c for c in snapshot.by_country()}
    assert by_country["Argentina"].total == 2
    assert by_country["Argentina"].done == 1
    assert by_country["Austria"].done == 1


def test_stage_url_and_flag():
    by_id = {s.stage_id: s for s in parse_stats(FIXTURE).stages}
    assert by_id[346].url.endswith("centerbox=rsfhotlap&stageid=346")
    assert by_id[346].flag == "🇦🇷"


def test_parse_leaderboard():
    board = parse_leaderboard(LEADERBOARD, 346)
    assert board.stage_id == 346
    assert board.count == 2
    first = board.entries[0]
    assert first.position == 1
    assert first.driver == "Tommi Hallman"
    assert first.driver_id == 14447
    assert first.car == "Skoda Fabia RS Rally2"
    assert first.checkpoints == ["1:08.034", "3:30.059"]
    assert first.finish_time == "4:45.756"
    assert first.diff_first == "00.000"
    assert first.uploaded == "2025-02-10 17:00:43"


def test_leaderboard_stage_metadata():
    board = parse_leaderboard(LEADERBOARD, 346)
    assert board.stage is not None
    assert board.stage.name == "Fernet Branca 2015"
    assert board.stage.country == "Argentina"
    assert board.stage.surface == "gravel"


def test_leaderboard_rank_and_cars():
    board = parse_leaderboard(LEADERBOARD, 346)
    assert board.find_rank(14447) == 1
    assert board.find_rank(999) == 2
    assert board.find_rank(123456) is None
    cars = dict(board.car_breakdown())
    assert cars["Skoda Fabia RS Rally2"] == 1
    assert cars["Ford Fiesta"] == 1


def test_by_surface_breakdown():
    snapshot = parse_stats(FIXTURE)
    by_surface = {s.surface: s for s in snapshot.by_surface()}
    assert by_surface["gravel"].total == 1
    assert by_surface["gravel"].done == 1
    assert by_surface["tarmac"].done == 0
    assert by_surface["gravel"].km_done == 6.0


def test_suggestions():
    snapshot = parse_stats(FIXTURE)
    sugg = snapshot.suggestions()
    # Only Otra Etapa (376) is not done -> the single shortest to-do candidate.
    assert [s.name for s in sugg["shortest"]] == ["Otra Etapa"]
    # Argentina has 1/2 done -> near completion.
    assert any(c.country == "Argentina" for c in sugg["near_countries"])


def test_strengths():
    snapshot = parse_stats(FIXTURE)
    by_id = {s.stage_id: s for s in snapshot.stages}
    # Two ranked gravel/snow stages: gravel top 10%, snow top 50%.
    by_id[346].my_rank, by_id[346].field_size = 10, 100  # gravel, top 10%
    by_id[101].my_rank, by_id[101].field_size = 50, 100  # snow, top 50%
    strengths = snapshot.strengths()
    by_surface = {s.label: s for s in strengths["by_surface"]}
    assert by_surface["gravel"].avg_percentile == 10.0
    assert by_surface["snow"].avg_percentile == 50.0
    # Sorted best-first: gravel before snow.
    assert strengths["by_surface"][0].label == "gravel"


def test_translate():
    from rsf_stats.translations import translate

    assert translate("nav.rivals", "fr") == "Rivaux"
    assert translate("nav.rivals", "en") == "Rivals"
    assert translate("nav.rivals", "de") == "Rivals"  # unknown lang -> english
    assert translate("does.not.exist", "fr") == "does.not.exist"


def test_percentile():
    snapshot = parse_stats(FIXTURE)
    by_id = {s.stage_id: s for s in snapshot.stages}
    by_id[346].my_rank = 5
    by_id[346].field_size = 100
    assert by_id[346].percentile == 5.0


CAREER_HTML = """
<table>
  <tr class="fejlec2"><td>Entered rallies :</td><td>3,056</td></tr>
  <tr class="fejlec2"><td>Finished rallies :</td><td>134(4.4%)</td></tr>
  <tr class="fejlec2"><td>Covered kilometeres:</td><td>4,060 Stage ~22,126 km</td></tr>
</table>
"""


def test_author_and_image():
    by_id = {s.stage_id: s for s in parse_stats(FIXTURE).stages}
    assert by_id[346].author == "RALLY Guru"
    assert by_id[346].image_url.endswith("/images/stages/346.jpg")


def test_seconds_to_str():
    assert seconds_to_str(68.034) == "1:08.034"
    assert seconds_to_str(15.697) == "15.697"
    assert seconds_to_str(None) is None


def test_entry_sectors():
    board = parse_leaderboard(LEADERBOARD, 346)
    assert board.entries[0].sectors == [68.034, 142.025, 75.697]
    assert board.entries[1].sectors == [69.0, 142.0, 79.1]


def test_sector_analysis_and_ideal():
    analysis = parse_leaderboard(LEADERBOARD, 346).sector_analysis()
    assert analysis.count == 3
    assert analysis.best_seconds == [68.034, 142.0, 75.697]
    assert analysis.best_driver == ["Tommi Hallman", "Second Driver", "Tommi Hallman"]
    assert analysis.ideal_seconds == 285.731  # sum of best sectors


def test_gain_potential():
    board = parse_leaderboard(LEADERBOARD, 346)
    # Tommi (14447) owns the best sectors 0 and 2, loses only sector 1 to driver 999.
    assert board.gain_potential(14447) == pytest.approx(0.025)  # 142.025 - 142.0
    # Driver 999 loses sectors 0 (69-68.034) and 2 (79.1-75.697).
    assert board.gain_potential(999) == pytest.approx(0.966 + 3.403, abs=1e-3)
    assert board.gain_potential(123456) is None  # not in the field


def test_activity_calendar():
    snapshot = parse_stats(FIXTURE)
    # give the two completed stages upload dates
    by_id = {s.stage_id: s for s in snapshot.stages}
    by_id[346].uploaded = "2026-06-15 10:00:00"
    by_id[101].uploaded = "2026-06-15 12:00:00"
    cal = snapshot.activity_calendar(weeks=8, today=date(2026, 6, 20))
    assert cal["max"] == 2  # both on the same day
    hit = [d for d in cal["days"] if d["date"] == "2026-06-15"]
    assert hit and hit[0]["count"] == 2


def test_parse_career():
    career = parse_career(CAREER_HTML)
    assert career.entered_rallies == 3056
    assert career.finished_rallies == 134
    assert career.finish_pct == 4.4
    assert career.stages_driven == 4060
    assert career.km_driven == 22126


def test_sector_ranks():
    board = parse_leaderboard(LEADERBOARD, 346)
    assert board.sector_ranks(14447) == [1, 2, 1]  # Tommi: best S0/S2, 2nd on S1
    assert board.sector_ranks(999) == [2, 1, 2]


def test_empty_catalog_raises():
    with pytest.raises(ScrapeError):
        parse_stats("<html><body>Please login</body></html>")


def test_flag_emoji_helper():
    assert flag_emoji("FR") == "🇫🇷"
    assert flag_emoji(None) == ""
    assert flag_emoji("XYZ") == ""


def test_time_to_seconds_helper():
    assert time_to_seconds("4:55.920") == pytest.approx(295.92)
    assert time_to_seconds("1:04.685") == pytest.approx(64.685)
    assert time_to_seconds("12.189") == pytest.approx(12.189)
    assert time_to_seconds(None) is None
