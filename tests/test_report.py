from helpers import at, date_range, interval, issue
from jira_activity.domain.report import build_report, sum_columns

PERIOD = date_range(at(1), at(5))


def test_build_report_keeps_only_issues_with_time_in_range():
    issues = [issue(at(1), key="ABC-1"), issue(at(1), key="ABC-2")]
    report = build_report(issues, {"ABC-1": [interval("To Do", at(1), at(2))], "ABC-2": []}, PERIOD)
    assert [i.key for i in report.issues] == ["ABC-1"]


def test_build_report_collects_every_section():
    intervals = {
        "ABC-1": [interval("To Do", at(1), at(2)), interval("Done", at(2), at(3))],
        "ABC-2": [interval("To Do", at(1), at(1, 12))],
    }
    report = build_report([issue(at(1), key="ABC-1"), issue(at(1), key="ABC-2")], intervals, PERIOD)
    assert report.statuses == ["To Do", "Done"]
    assert report.hours_by_ticket == {"ABC-1": {"To Do": 24.0, "Done": 24.0}, "ABC-2": {"To Do": 12.0}}
    assert report.hours_by_status == {"To Do": 36.0, "Done": 24.0}
    assert report.tickets_by_status == {"To Do": ["ABC-1", "ABC-2"], "Done": ["ABC-1"]}
    assert report.matrix_status_totals == {"To Do": 36.0, "Done": 24.0}
    assert report.date_range == PERIOD


def test_sum_columns_adds_rounded_cells_and_fills_missing_with_zero():
    hours = {"ABC-1": {"To Do": 0.1, "Done": 1.0}, "ABC-2": {"To Do": 0.1}}
    assert sum_columns(hours, ["To Do", "Done", "Review"]) == {"To Do": 0.2, "Done": 1.0, "Review": 0.0}
