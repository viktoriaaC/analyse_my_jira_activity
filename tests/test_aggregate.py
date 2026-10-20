import pytest

from helpers import at, change, date_range, interval, issue
from jira_activity.domain.aggregate import hours_per_ticket_status, tickets_per_status, time_per_status
from jira_activity.domain.timeline import build_intervals, clip


def test_hours_per_status_for_simple_flow():
    changes = [
        change(at(1, 14), "To Do", "In Progress"),
        change(at(1, 16), "In Progress", "Done"),
    ]
    intervals = build_intervals(issue(at(1, 10)), changes, now=at(1, 16))
    assert hours_per_ticket_status({"ABC-1": intervals}) == {
        "ABC-1": {"To Do": 4.0, "In Progress": 2.0}
    }


def test_hours_are_summed_when_ticket_returns_to_a_status():
    intervals = [
        interval("In Progress", at(1, 0), at(1, 3)),
        interval("Review", at(1, 3), at(1, 4)),
        interval("In Progress", at(1, 4), at(1, 6)),
    ]
    result = hours_per_ticket_status({"ABC-1": intervals})
    assert result["ABC-1"] == {"In Progress": 5.0, "Review": 1.0}


def test_hours_are_clipped_at_range_edges():
    intervals = [interval("In Progress", at(1), at(10))]
    clipped = clip(intervals, date_range(at(2), at(3)))
    assert hours_per_ticket_status({"ABC-1": clipped}) == {"ABC-1": {"In Progress": 24.0}}


def test_ticket_row_adds_up_to_time_inside_range():
    changes = [
        change(at(2, 7), "To Do", "In Progress"),
        change(at(3, 19), "In Progress", "Review"),
        change(at(4, 2), "Review", "Done"),
    ]
    the_range = date_range(at(2), at(5))
    clipped = clip(build_intervals(issue(at(1)), changes, now=at(9)), the_range)
    row = hours_per_ticket_status({"ABC-1": clipped})["ABC-1"]
    range_hours = (the_range.end - the_range.start).total_seconds() / 3600
    assert sum(row.values()) == pytest.approx(range_hours, abs=0.1 * len(row))


def test_hours_are_rounded_to_one_decimal():
    intervals = [interval("To Do", at(1, 0), at(1, 1).replace(minute=20))]
    assert hours_per_ticket_status({"ABC-1": intervals}) == {"ABC-1": {"To Do": 1.3}}


def test_tickets_without_intervals_are_left_out():
    assert hours_per_ticket_status({"ABC-1": []}) == {}


def test_time_per_status_totals_all_tickets():
    intervals_by_issue = {
        "ABC-1": [interval("To Do", at(1, 0), at(1, 2))],
        "ABC-2": [interval("To Do", at(1, 0), at(1, 3)), interval("Done", at(1, 3), at(1, 4))],
    }
    assert time_per_status(intervals_by_issue) == {"To Do": 5.0, "Done": 1.0}


def test_tickets_per_status_lists_each_ticket_once_sorted():
    intervals_by_issue = {
        "ABC-2": [interval("To Do", at(1, 0), at(1, 1)), interval("To Do", at(1, 2), at(1, 3))],
        "ABC-1": [interval("To Do", at(1, 0), at(1, 1)), interval("Done", at(1, 1), at(1, 2))],
    }
    assert tickets_per_status(intervals_by_issue) == {
        "To Do": ["ABC-1", "ABC-2"],
        "Done": ["ABC-1"],
    }
