"""
Shared "Date Range" preset → cutoff-date logic (W11-03).

Both PR Records (list filtering) and the Dashboard (spending aggregation)
expose the same Date Range dropdown, so the preset-to-date mapping lives here
once and is imported by both endpoints. Presets mirror the frontend FilterBar
options exactly.

Filtering is on the PR's ``request_date`` (the xlsx "PR Sub Date").
"""

from __future__ import annotations

from datetime import date, timedelta

# Mirror of the frontend FilterBar "Date Range" option values.
DATE_RANGE_PRESETS = {"all", "7d", "30d", "90d", "ytd"}


def date_range_cutoff(preset: str | None, today: date | None = None) -> date | None:
    """
    Map a Date Range preset to the earliest ``request_date`` to include.

    Returns ``None`` when no lower bound applies ("all", empty, or an
    unrecognised value) — callers should then apply no date filter.
    The bound is inclusive: callers filter ``request_date >= cutoff``.

    ``today`` is injectable so the logic is deterministically testable.
    """
    today = today or date.today()
    if preset == "7d":
        return today - timedelta(days=7)
    if preset == "30d":
        return today - timedelta(days=30)
    if preset == "90d":
        return today - timedelta(days=90)
    if preset == "ytd":
        return date(today.year, 1, 1)
    return None


def fiscal_year_bounds(today: date | None = None) -> tuple[date, date]:
    """
    Inclusive (start, end) of the current fiscal year (Apr 1 → Mar 31).

    Mirrors config.get_or_create_current_period: months before April belong to
    the prior year's FY. e.g. 2026-07-01 → (2026-04-01, 2027-03-31).
    """
    today = today or date.today()
    start_year = today.year if today.month >= 4 else today.year - 1
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


def date_range_bounds(
    preset: str | None, today: date | None = None
) -> tuple[date | None, date | None]:
    """
    Inclusive (start, end) bounds for a Date Range preset, used by the dashboard
    where the fiscal-year option needs an upper bound too.

    - "fy"               → the full current fiscal year span.
    - 7d / 30d / 90d/ytd → (cutoff, None): a lower bound only, up to today.
    - "all" / None / etc → (None, None): no filter.
    """
    today = today or date.today()
    if preset == "fy":
        return fiscal_year_bounds(today)
    return date_range_cutoff(preset, today), None
