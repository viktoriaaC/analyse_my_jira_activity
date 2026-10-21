from datetime import date, timezone

import pytest

from helpers import at, interval
from jira_activity.domain.models import DateRange, parse_day
from jira_activity.errors import DateRangeTooLongError, InvalidDateRangeError


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


def test_date_range_allows_366_days():
    result = DateRange.from_dates(date(2028, 1, 1), date(2028, 12, 31), timezone.utc)
    assert (result.end - result.start).days == 366


def test_date_range_rejects_more_than_366_days():
    with pytest.raises(DateRangeTooLongError) as error:
        DateRange.from_dates(date(2026, 1, 1), date(2027, 1, 2), timezone.utc)
    assert error.value.code == "JA-204"
    assert "367 days" in str(error.value)


def test_parse_day_reads_iso_date():
    assert parse_day(" 2026-10-05 ") == date(2026, 10, 5)


@pytest.mark.parametrize("text", ["2026-13-01", "05/10/2026", "20261005", "yesterday", ""])
def test_parse_day_rejects_other_formats(text):
    with pytest.raises(InvalidDateRangeError) as error:
        parse_day(text)
    assert error.value.code == "JA-201"


def test_interval_hours():
    assert interval("To Do", at(1, 10), at(1, 14)).hours == 4.0
