"""Terminal output of the report, using rich.

This module only formats: every number comes from the domain layer.
"""

from datetime import timedelta

from rich.console import Console
from rich.table import Table
from rich.text import Text

from jira_activity.domain.aggregate import (
    IntervalsByIssue,
    hours_per_ticket_status,
    status_order,
    tickets_per_status,
    time_per_status,
)
from jira_activity.domain.models import DateRange, Issue, StatusInterval
from jira_activity.domain.timeline import status_at

STATUS_COLORS = [
    "blue", "yellow", "green", "magenta", "cyan", "red",
    "bright_blue", "bright_yellow", "bright_green", "bright_magenta",
]
BAR = "█"
GAP = "·"
EMPTY_CELL = "–"
DATE_FORMAT = "%Y-%m-%d"
LABEL_WIDTH = 12
MIN_TIMELINE_WIDTH = 20
MAX_TIMELINE_WIDTH = 100
SUMMARY_MAX_WIDTH = 40


def render_report(
    console: Console,
    issues: list[Issue],
    intervals_by_issue: IntervalsByIssue,
    date_range: DateRange,
) -> None:
    """Print the whole report: title, summary, timeline, tickets per status and hours matrix."""
    shown = [issue for issue in issues if intervals_by_issue.get(issue.key)]
    render_title(console, date_range, len(shown))
    if not shown:
        console.print("No tickets were assigned to you in this period.")
        return
    statuses = status_order(intervals_by_issue)
    colors = assign_colors(statuses)
    hours = hours_per_ticket_status(intervals_by_issue)
    keys_by_status = tickets_per_status(intervals_by_issue)
    render_summary(console, statuses, time_per_status(intervals_by_issue), keys_by_status, colors)
    render_timeline(console, shown, intervals_by_issue, date_range, colors)
    render_tickets_per_status(console, shown, statuses, keys_by_status, hours, colors)
    render_hours_matrix(console, shown, statuses, hours)


def render_title(console: Console, date_range: DateRange, ticket_count: int) -> None:
    """Print the report heading with the period and number of tickets."""
    first, last = period_labels(date_range)
    console.print(Text(f"Jira activity {first} – {last}", style="bold"))
    console.print(f"{ticket_count} ticket(s) assigned to you in the period. Hours are calendar hours.\n")


def render_summary(
    console: Console,
    statuses: list[str],
    hours_by_status: dict[str, float],
    keys_by_status: dict[str, list[str]],
    colors: dict[str, str],
) -> None:
    """Print total hours and number of tickets per status."""
    table = Table(title="Time per status")
    table.add_column("Status")
    table.add_column("Hours", justify="right")
    table.add_column("Tickets", justify="right")
    for status in statuses:
        table.add_row(Text(status, style=colors[status]), format_hours(hours_by_status[status]), str(len(keys_by_status[status])))
    console.print(table)
    console.print()


def render_timeline(
    console: Console,
    issues: list[Issue],
    intervals_by_issue: IntervalsByIssue,
    date_range: DateRange,
    colors: dict[str, str],
) -> None:
    """Print one coloured bar per ticket over the period, with a date axis and a legend."""
    width = timeline_width(console)
    table = Table(title="Status timeline", show_edge=False, pad_edge=False)
    table.add_column("Ticket", width=LABEL_WIDTH, no_wrap=True)
    table.add_column(date_axis(date_range, width), no_wrap=True)
    for issue in issues:
        table.add_row(Text(issue.key), timeline_bar(intervals_by_issue[issue.key], date_range, width, colors))
    console.print(table)
    console.print(legend(colors))
    console.print()


def render_tickets_per_status(
    console: Console,
    issues: list[Issue],
    statuses: list[str],
    keys_by_status: dict[str, list[str]],
    hours: dict[str, dict[str, float]],
    colors: dict[str, str],
) -> None:
    """Print, for each status, the tickets that were in it and for how many hours."""
    summaries = {issue.key: issue.summary for issue in issues}
    table = Table(title="Tickets per status")
    table.add_column("Status")
    table.add_column("Ticket", no_wrap=True)
    table.add_column("Summary", max_width=SUMMARY_MAX_WIDTH, overflow="ellipsis", no_wrap=True)
    table.add_column("Hours", justify="right")
    for status in statuses:
        for index, key in enumerate(keys_by_status[status]):
            label = Text(status, style=colors[status]) if index == 0 else ""
            table.add_row(label, Text(key), Text(summaries[key]), format_hours(hours[key][status]))
        table.add_section()
    console.print(table)
    console.print()


def render_hours_matrix(
    console: Console,
    issues: list[Issue],
    statuses: list[str],
    hours: dict[str, dict[str, float]],
) -> None:
    """Print hours per ticket and status, with a total per ticket and per status."""
    status_totals = {status: sum(hours[issue.key].get(status, 0.0) for issue in issues) for status in statuses}
    table = Table(title="Hours per status", show_footer=True)
    table.add_column("Ticket", footer="Total", no_wrap=True)
    table.add_column("Summary", max_width=SUMMARY_MAX_WIDTH, overflow="ellipsis", no_wrap=True)
    for status in statuses:
        table.add_column(Text(status), justify="right", footer=format_hours(status_totals[status]))
    table.add_column("Total h", justify="right", footer=format_hours(sum(status_totals.values())))
    for issue in issues:
        row = hours[issue.key]
        cells = [format_hours(row.get(status)) for status in statuses]
        table.add_row(Text(issue.key), Text(issue.summary), *cells, format_hours(sum(row.values())))
    console.print(table)


def assign_colors(statuses: list[str]) -> dict[str, str]:
    """Give each status its own colour, cycling if there are more statuses than colours."""
    return {status: STATUS_COLORS[index % len(STATUS_COLORS)] for index, status in enumerate(statuses)}


def format_hours(hours: float | None) -> str:
    """Show hours with one decimal, or a dash when there are none."""
    return EMPTY_CELL if hours is None else f"{round(hours, 1):.1f}"


def period_labels(date_range: DateRange) -> tuple[str, str]:
    """Return the first and last day of the range as text. The range end is exclusive."""
    last_day = date_range.end - timedelta(days=1)
    return date_range.start.strftime(DATE_FORMAT), last_day.strftime(DATE_FORMAT)


def timeline_width(console: Console) -> int:
    """Number of characters available for the timeline bars."""
    available = console.width - LABEL_WIDTH - 4
    return max(MIN_TIMELINE_WIDTH, min(MAX_TIMELINE_WIDTH, available))


def date_axis(date_range: DateRange, width: int) -> str:
    """Return the first date on the left and the last date on the right of a line of the given width."""
    first, last = period_labels(date_range)
    return first + last.rjust(width - len(first))


def timeline_bar(
    intervals: list[StatusInterval],
    date_range: DateRange,
    width: int,
    colors: dict[str, str],
) -> Text:
    """Draw one character per time slot, coloured by the status at the middle of the slot."""
    slot = (date_range.end - date_range.start) / width
    bar = Text()
    for index in range(width):
        status = status_at(intervals, date_range.start + slot * (index + 0.5))
        if status:
            bar.append(BAR, style=colors[status])
        else:
            bar.append(GAP, style="dim")
    return bar


def legend(colors: dict[str, str]) -> Text:
    """Return a line explaining which colour belongs to which status."""
    text = Text("Legend: ")
    for status, color in colors.items():
        text.append(BAR, style=color)
        text.append(f" {status}  ")
    text.append(f"{GAP} not created yet", style="dim")
    return text
