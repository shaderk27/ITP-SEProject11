"""
Unit tests for the shared Date Range cutoff helper (W11-03).

Pure function, no DB — uses an injected ``today`` so the boundaries are
deterministic.
"""

from __future__ import annotations

from datetime import date

from app.utils.date_range import date_range_cutoff

# Fixed reference date for all cases.
TODAY = date(2026, 7, 1)


def test_all_returns_no_cutoff():
    assert date_range_cutoff("all", today=TODAY) is None


def test_none_and_unknown_return_no_cutoff():
    assert date_range_cutoff(None, today=TODAY) is None
    assert date_range_cutoff("bogus", today=TODAY) is None


def test_relative_presets():
    assert date_range_cutoff("7d", today=TODAY) == date(2026, 6, 24)
    assert date_range_cutoff("30d", today=TODAY) == date(2026, 6, 1)
    assert date_range_cutoff("90d", today=TODAY) == date(2026, 4, 2)


def test_ytd_is_jan_first_of_current_year():
    assert date_range_cutoff("ytd", today=TODAY) == date(2026, 1, 1)
