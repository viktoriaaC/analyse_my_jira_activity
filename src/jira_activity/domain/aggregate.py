"""Summaries of clipped status intervals.

Every function takes a mapping of issue key to that issue's intervals,
already clipped to the requested date range. Hours are calendar hours unless
another measure is given, and are rounded to one decimal.
"""

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime

from jira_activity.domain.models import StatusInterval

IntervalsByIssue = dict[str, list[StatusInterval]]
HoursMeasure = Callable[[StatusInterval], float]

HOURS_DECIMALS = 1


def calendar_hours(interval: StatusInterval) -> float:
    """Count every hour of the interval."""
    return interval.hours


def hours_per_ticket_status(
    intervals_by_issue: IntervalsByIssue,
    measure: HoursMeasure = calendar_hours,
) -> dict[str, dict[str, float]]:
    """Return hours spent in each status, per ticket. Repeat visits to a status are summed."""
    return {
        key: _sum_hours_by_status(intervals, measure)
        for key, intervals in intervals_by_issue.items()
        if intervals
    }


def hours_per_status(
    intervals_by_issue: IntervalsByIssue,
    measure: HoursMeasure = calendar_hours,
) -> dict[str, float]:
    """Return total hours spent in each status, over all tickets."""
    all_intervals = [interval for intervals in intervals_by_issue.values() for interval in intervals]
    return _sum_hours_by_status(all_intervals, measure)


def tickets_per_status(intervals_by_issue: IntervalsByIssue) -> dict[str, list[str]]:
    """Return the sorted keys of the tickets that were in each status."""
    keys_by_status: dict[str, set[str]] = defaultdict(set)
    for key, intervals in intervals_by_issue.items():
        for interval in intervals:
            keys_by_status[interval.status].add(key)
    return {status: sorted(keys) for status, keys in keys_by_status.items()}


def status_order(intervals_by_issue: IntervalsByIssue) -> list[str]:
    """Return statuses in the order they first appear, which usually follows the workflow."""
    first_seen: dict[str, datetime] = {}
    for intervals in intervals_by_issue.values():
        for interval in intervals:
            if interval.status not in first_seen or interval.start < first_seen[interval.status]:
                first_seen[interval.status] = interval.start
    return sorted(first_seen, key=lambda status: (first_seen[status], status))


def _sum_hours_by_status(intervals: list[StatusInterval], measure: HoursMeasure) -> dict[str, float]:
    """Add up the measured hours per status and round the totals."""
    totals: dict[str, float] = defaultdict(float)
    for interval in intervals:
        totals[interval.status] += measure(interval)
    return {status: round(hours, HOURS_DECIMALS) for status, hours in totals.items()}
