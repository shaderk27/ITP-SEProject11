"""
Unit tests for the shared Date Range cutoff helper (W11-03).

Pure function, no DB — uses an injected ``today`` so the boundaries are
deterministic.
"""

from __future__ import annotations

from datetime import date

from app.utils.date_range import (
    date_range_bounds,
    date_range_cutoff,
    fiscal_year_bounds,
)

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


def test_fiscal_year_bounds_spans_april_to_march():
    # 2026-07-01 is in FY2026 (Apr 2026 → Mar 2027).
    assert fiscal_year_bounds(TODAY) == (date(2026, 4, 1), date(2027, 3, 31))


def test_fiscal_year_bounds_before_april_belongs_to_prior_fy():
    assert fiscal_year_bounds(date(2026, 2, 15)) == (
        date(2025, 4, 1),
        date(2026, 3, 31),
    )


def test_date_range_bounds_fy_has_both_ends():
    assert date_range_bounds("fy", today=TODAY) == (date(2026, 4, 1), date(2027, 3, 31))


def test_date_range_bounds_relative_is_lower_bound_only():
    assert date_range_bounds("30d", today=TODAY) == (date(2026, 6, 1), None)


def test_date_range_bounds_all_is_unbounded():
    assert date_range_bounds("all", today=TODAY) == (None, None)
