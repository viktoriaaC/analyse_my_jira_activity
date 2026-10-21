"""Turn an issue's status changes into status intervals and clip them to a date range."""

from datetime import datetime

from jira_activity.domain.models import DateRange, Issue, StatusChange, StatusInterval


def initial_status(issue: Issue, changes: list[StatusChange]) -> str:
    """Return the status the issue had when it was created."""
    return changes[0].from_status if changes else issue.status


def build_intervals(issue: Issue, changes: list[StatusChange], now: datetime) -> list[StatusInterval]:
    """Split the issue's life from creation until now into one interval per status.

    Each change ends the current interval and starts the next one.
    The last interval stays open until `now`. Empty intervals are dropped.
    """
    ordered = sorted(changes, key=lambda change: change.at)
    intervals = []
    status, start = initial_status(issue, ordered), issue.created
    for change in ordered:
        intervals.append(StatusInterval(status, start, change.at))
        status, start = change.to_status, change.at
    intervals.append(StatusInterval(status, start, now))
    return [interval for interval in intervals if interval.end > interval.start]


def intervals_in_range(
    issues: list[Issue],
    changes_by_key: dict[str, list[StatusChange]],
    date_range: DateRange,
    now: datetime,
) -> dict[str, list[StatusInterval]]:
    """Return each issue's status intervals, clipped to the date range."""
    return {
        issue.key: clip(build_intervals(issue, changes_by_key.get(issue.key, []), now), date_range)
        for issue in issues
    }


def status_at(intervals: list[StatusInterval], moment: datetime) -> str | None:
    """Return the status at the given moment, or None if no interval covers it."""
    for interval in intervals:
        if interval.start <= moment < interval.end:
            return interval.status
    return None


def clip(intervals: list[StatusInterval], date_range: DateRange) -> list[StatusInterval]:
    """Cut the intervals to the date range and drop the ones that fall outside it."""
    clipped = (
        StatusInterval(
            interval.status,
            max(interval.start, date_range.start),
            min(interval.end, date_range.end),
        )
        for interval in intervals
    )
    return [interval for interval in clipped if interval.end > interval.start]
