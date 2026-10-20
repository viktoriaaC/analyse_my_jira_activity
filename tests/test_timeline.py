from helpers import at, change, date_range, interval, issue
from jira_activity.domain.timeline import build_intervals, clip


def test_no_changes_gives_one_interval_in_current_status():
    result = build_intervals(issue(at(1), status="To Do"), [], now=at(3))
    assert result == [interval("To Do", at(1), at(3))]


def test_changes_split_life_into_intervals():
    changes = [
        change(at(2), "To Do", "In Progress"),
        change(at(4), "In Progress", "Done"),
    ]
    result = build_intervals(issue(at(1)), changes, now=at(6))
    assert result == [
        interval("To Do", at(1), at(2)),
        interval("In Progress", at(2), at(4)),
        interval("Done", at(4), at(6)),
    ]


def test_changes_are_sorted_by_time():
    changes = [
        change(at(4), "In Progress", "Done"),
        change(at(2), "To Do", "In Progress"),
    ]
    result = build_intervals(issue(at(1)), changes, now=at(6))
    assert [i.status for i in result] == ["To Do", "In Progress", "Done"]


def test_last_interval_stays_open_until_now():
    changes = [change(at(2), "To Do", "In Progress")]
    result = build_intervals(issue(at(1)), changes, now=at(9, 12))
    assert result[-1] == interval("In Progress", at(2), at(9, 12))


def test_zero_length_intervals_are_dropped():
    changes = [change(at(1), "To Do", "In Progress")]
    result = build_intervals(issue(at(1)), changes, now=at(2))
    assert result == [interval("In Progress", at(1), at(2))]


def test_clip_cuts_intervals_crossing_range_edges():
    intervals = [interval("To Do", at(1), at(5)), interval("Done", at(5), at(10))]
    result = clip(intervals, date_range(at(3), at(7)))
    assert result == [interval("To Do", at(3), at(5)), interval("Done", at(5), at(7))]


def test_clip_drops_intervals_before_and_after_range():
    intervals = [
        interval("To Do", at(1), at(2)),
        interval("In Progress", at(2), at(4)),
        interval("Done", at(4), at(9)),
    ]
    result = clip(intervals, date_range(at(2, 12), at(3)))
    assert result == [interval("In Progress", at(2, 12), at(3))]


def test_clip_keeps_ticket_created_inside_range_from_creation():
    intervals = build_intervals(issue(at(5), status="To Do"), [], now=at(20))
    result = clip(intervals, date_range(at(1), at(10)))
    assert result == [interval("To Do", at(5), at(10))]


def test_clip_returns_nothing_when_ticket_created_after_range():
    intervals = build_intervals(issue(at(15), status="To Do"), [], now=at(20))
    assert clip(intervals, date_range(at(1), at(10))) == []
