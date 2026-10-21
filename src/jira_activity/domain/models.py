"""Plain data types shared by the domain logic, the adapters and the CLI."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from jira_activity.errors import DateRangeTooLongError, InvalidDateRangeError

DAY_FORMAT = "%Y-%m-%d"
# Every ticket in the range costs at least one Jira request, so very long ranges are refused.
MAX_RANGE_DAYS = 366


def parse_day(text: str) -> date:
    """Parse a day written as YYYY-MM-DD."""
    try:
        return datetime.strptime(text.strip(), DAY_FORMAT).date()
    except ValueError as error:
        raise InvalidDateRangeError(f"'{text}' is not a valid YYYY-MM-DD date") from error


@dataclass(frozen=True)
class DateRange:
    """A half-open time range [start, end) with timezone-aware datetimes."""

    start: datetime
    end: datetime

    @classmethod
    def from_dates(cls, first_day: date, last_day: date, tz: tzinfo) -> "DateRange":
        """Build a range covering whole days, from first_day 00:00 up to the end of last_day."""
        if first_day > last_day:
            raise InvalidDateRangeError(f"{first_day} is after {last_day}")
        days = (last_day - first_day).days + 1
        if days > MAX_RANGE_DAYS:
            raise DateRangeTooLongError(f"{days} days requested")
        start = datetime.combine(first_day, time.min, tzinfo=tz)
        end = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=tz)
        return cls(start=start, end=end)


@dataclass(frozen=True)
class Issue:
    """The fields of a Jira issue that the analysis needs."""

    key: str
    summary: str
    status: str
    created: datetime


@dataclass(frozen=True)
class StatusChange:
    """One status transition taken from an issue's changelog."""

    at: datetime
    from_status: str
    to_status: str


@dataclass(frozen=True)
class StatusInterval:
    """A period during which an issue was in one status."""

    status: str
    start: datetime
    end: datetime

    @property
    def hours(self) -> float:
        """Length of the interval in calendar hours."""
        return (self.end - self.start).total_seconds() / 3600
