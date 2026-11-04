from datetime import datetime, timedelta, timezone

import pytest

from helpers import at, interval
from jira_activity.domain.work_hours import work_hours_in

# In October 2026, the 1st is a Thursday, the 2nd a Friday, the 3rd and 4th a weekend and the 5th a Monday.


def in_utc(moment):
    return moment.astimezone(timezone.utc)


def in_offset(hours):
    return lambda moment: moment.astimezone(timezone(timedelta(hours=hours)))


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (at(1, 10), at(1, 12), 2.0),
        (at(1, 6), at(1, 20), 9.0),
        (at(1, 6), at(1, 9), 1.0),
        (at(1, 16), at(1, 20), 1.0),
        (at(1, 0), at(1, 8), 0.0),
        (at(1, 17), at(2, 8), 0.0),
        (at(3, 0), at(5, 0), 0.0),
        (at(2, 16), at(5, 9), 2.0),
        (at(1, 0), at(6, 0), 27.0),
    ],
    ids=[
        "inside-a-workday",
        "whole-workday",
        "starts-before-opening",
        "ends-after-closing",
        "night-before-opening",
        "evening-to-next-morning",
        "whole-weekend",
        "friday-to-monday",
        "several-days",
    ],
)
def test_work_hours_in_interval(start, end, expected):
    assert work_hours_in(interval("To Do", start, end), in_utc) == expected


def test_minutes_are_counted():
    start = at(1, 8).replace(minute=30)
    assert work_hours_in(interval("To Do", start, at(1, 9)), in_utc) == 0.5


def test_work_hours_follow_the_local_clock():
    # 06:00-15:00 UTC is exactly 08:00-17:00 at UTC+2.
    whole_day = interval("To Do", at(1, 6), at(1, 15))
    assert work_hours_in(whole_day, in_offset(2)) == 9.0
    assert work_hours_in(whole_day, in_utc) == 7.0


def test_weekend_follows_the_local_clock():
    # Saturday 00:00-02:00 UTC is still Friday evening at UTC-8, 16:00-18:00.
    around_midnight = interval("To Do", at(3, 0), at(3, 2))
    assert work_hours_in(around_midnight, in_utc) == 0.0
    assert work_hours_in(around_midnight, in_offset(-8)) == 1.0


def test_each_end_uses_the_utc_offset_of_its_own_date():
    # Summer time ends on Sunday 25 October 2026 in Sweden: UTC+2 before, UTC+1 after.
    def in_sweden(moment):
        return in_offset(2 if moment < datetime(2026, 10, 25, 1, tzinfo=timezone.utc) else 1)(moment)

    # Friday 08:00 local to Monday 09:00 local: the whole of Friday plus one hour on Monday.
    over_the_change = interval("To Do", at(23, 6), at(26, 8))
    assert work_hours_in(over_the_change, in_sweden) == 10.0
