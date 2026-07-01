"""Tests for pure helpers in the app layer."""

from __future__ import annotations

from rsf_stats.app import _championship


def test_championship_points():
    # A wins stage 1, B wins stage 2 -> 1 point each, 1 win each.
    driver_times = {
        "A": {1: 10.0, 2: 20.0},
        "B": {1: 11.0, 2: 19.0},
    }
    table = _championship(driver_times)
    by_name = {r["name"]: r for r in table}
    assert by_name["A"]["points"] == 1
    assert by_name["B"]["points"] == 1
    assert by_name["A"]["wins"] == 1
    assert by_name["B"]["wins"] == 1
    assert by_name["A"]["contested"] == 2


def test_championship_dominant():
    driver_times = {
        "Fast": {1: 10.0, 2: 20.0, 3: 30.0},
        "Mid": {1: 11.0, 2: 21.0, 3: 31.0},
        "Slow": {1: 12.0, 2: 22.0},  # only 2 shared stages
    }
    table = _championship(driver_times)
    assert table[0]["name"] == "Fast"  # beats everyone on every stage
    assert table[0]["wins"] == 3
