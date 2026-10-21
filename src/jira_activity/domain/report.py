"""Everything the report shows, computed in one place so the renderer only has to format it."""

from dataclasses import dataclass

from jira_activity.domain.aggregate import (
    IntervalsByIssue,
    hours_per_ticket_status,
    status_order,
    tickets_per_status,
    time_per_status,
)
from jira_activity.domain.models import DateRange, Issue


@dataclass(frozen=True)
class Report:
    """The numbers behind every section of the report."""

    date_range: DateRange
    issues: list[Issue]
    intervals_by_issue: IntervalsByIssue
    statuses: list[str]
    hours_by_ticket: dict[str, dict[str, float]]
    hours_by_status: dict[str, float]
    tickets_by_status: dict[str, list[str]]
    matrix_status_totals: dict[str, float]


def build_report(issues: list[Issue], intervals_by_issue: IntervalsByIssue, date_range: DateRange) -> Report:
    """Compute the report for the issues that have any time inside the range."""
    shown = [issue for issue in issues if intervals_by_issue.get(issue.key)]
    statuses = status_order(intervals_by_issue)
    hours_by_ticket = hours_per_ticket_status(intervals_by_issue)
    return Report(
        date_range=date_range,
        issues=shown,
        intervals_by_issue=intervals_by_issue,
        statuses=statuses,
        hours_by_ticket=hours_by_ticket,
        hours_by_status=time_per_status(intervals_by_issue),
        tickets_by_status=tickets_per_status(intervals_by_issue),
        matrix_status_totals=sum_columns(hours_by_ticket, statuses),
    )


def sum_columns(hours_by_ticket: dict[str, dict[str, float]], statuses: list[str]) -> dict[str, float]:
    """Add up the (already rounded) hours of each status column, so the table sums correctly on screen."""
    return {status: sum(row.get(status, 0.0) for row in hours_by_ticket.values()) for status in statuses}
