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
