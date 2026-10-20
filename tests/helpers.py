from datetime import datetime, timezone

from jira_activity.domain.models import DateRange, Issue, StatusChange, StatusInterval


def at(day: int, hour: int = 0) -> datetime:
    """A UTC datetime in October 2026."""
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def issue(created: datetime, status: str = "Done", key: str = "ABC-1") -> Issue:
    return Issue(key=key, summary="A ticket", status=status, created=created)


def change(when: datetime, from_status: str, to_status: str) -> StatusChange:
    return StatusChange(at=when, from_status=from_status, to_status=to_status)


def interval(status: str, start: datetime, end: datetime) -> StatusInterval:
    return StatusInterval(status=status, start=start, end=end)


def date_range(start: datetime, end: datetime) -> DateRange:
    return DateRange(start=start, end=end)
