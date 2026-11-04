"""How much of a status interval falls within work hours: Monday to Friday, 08:00 to 17:00."""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta

from jira_activity.domain.models import StatusInterval

WORK_START = time(8)
WORK_END = time(17)
LAST_WORKDAY = 4  # date.weekday() counts Monday as 0, so 4 is Friday.
WORK_HOURS_LABEL = "Mon–Fri 08:00–17:00"


def work_hours_in(interval: StatusInterval, to_local: Callable[[datetime], datetime]) -> float:
    """Return the hours of the interval that fall within work hours.

    Work hours are wall clock times, so both ends are compared as local time without a timezone.
    `to_local` must use the UTC offset of the moment it converts, not today's, or an interval
    in another daylight-saving period is shifted by an hour.
    """
    start = to_local(interval.start).replace(tzinfo=None)
    end = to_local(interval.end).replace(tzinfo=None)
    worked = timedelta()
    day = start.date()
    while day <= end.date():
        worked += _work_time_on_day(day, start, end)
        day += timedelta(days=1)
    return worked.total_seconds() / 3600


def _work_time_on_day(day: date, start: datetime, end: datetime) -> timedelta:
    """Return how much of start..end falls within the work hours of this day."""
    if day.weekday() > LAST_WORKDAY:
        return timedelta()
    overlap = min(end, datetime.combine(day, WORK_END)) - max(start, datetime.combine(day, WORK_START))
    return max(overlap, timedelta())
