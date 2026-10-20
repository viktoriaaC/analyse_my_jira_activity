from datetime import date, timezone

import pytest

from helpers import at, interval
from jira_activity.domain.models import DateRange
from jira_activity.errors import InvalidDateRangeError


def test_date_range_covers_whole_days():
    result = DateRange.from_dates(date(2026, 10, 1), date(2026, 10, 2), timezone.utc)
    assert result.start == at(1)
    assert result.end == at(3)


def test_date_range_allows_single_day():
    result = DateRange.from_dates(date(2026, 10, 5), date(2026, 10, 5), timezone.utc)
    assert result.end - result.start == at(2) - at(1)


def test_date_range_rejects_start_after_end():
    with pytest.raises(InvalidDateRangeError) as error:
        DateRange.from_dates(date(2026, 10, 2), date(2026, 10, 1), timezone.utc)
    assert error.value.code == "JA-201"


def test_interval_hours():
    assert interval("To Do", at(1, 10), at(1, 14)).hours == 4.0
