"""Terminal output of the report, using rich.

This module only formats: every number comes from domain.report.Report.
Jira data (keys, summaries, statuses) is always wrapped in Text so rich never reads it as markup.
"""

from datetime import timedelta

from rich.console import Console
from rich.table import Table
from rich.text import Text

from jira_activity.domain.models import DateRange, StatusInterval
from jira_activity.domain.report import Report
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
# Column separator and padding that the timeline table adds around the bar.
TABLE_CHROME_WIDTH = 4
MIN_TIMELINE_WIDTH = 20
MAX_TIMELINE_WIDTH = 100
SUMMARY_MAX_WIDTH = 40


def render_report(console: Console, report: Report) -> None:
    """Print the whole report: title, summary, timeline, tickets per status and hours matrix."""
    render_title(console, report)
    if not report.issues:
        console.print("No tickets were assigned to you in this period.")
        return
    colors = assign_colors(report.statuses)
    render_summary(console, report, colors)
    render_timeline(console, report, colors)
    render_tickets_per_status(console, report, colors)
    render_hours_matrix(console, report)


def render_title(console: Console, report: Report) -> None:
    """Print the report heading with the period and number of tickets."""
    first, last = period_labels(report.date_range)
    console.print(Text(f"Jira activity {first} – {last}", style="bold"))
    console.print(f"{len(report.issues)} ticket(s) assigned to you in the period. Hours are calendar hours.\n")


def render_summary(console: Console, report: Report, colors: dict[str, str]) -> None:
    """Print total hours and number of tickets per status."""
    table = Table(title="Time per status")
    table.add_column("Status")
    table.add_column("Hours", justify="right")
    table.add_column("Tickets", justify="right")
    for status in report.statuses:
        table.add_row(
            Text(status, style=colors[status]),
            format_hours(report.hours_by_status[status]),
            str(len(report.tickets_by_status[status])),
        )
    console.print(table)
    console.print()


def render_timeline(console: Console, report: Report, colors: dict[str, str]) -> None:
    """Print one coloured bar per ticket over the period, with a date axis and a legend."""
    width = timeline_width(console)
    table = Table(title="Status timeline", show_edge=False, pad_edge=False)
    table.add_column("Ticket", width=LABEL_WIDTH, no_wrap=True)
    table.add_column(date_axis(report.date_range, width), no_wrap=True)
    for issue in report.issues:
        bar = timeline_bar(report.intervals_by_issue[issue.key], report.date_range, width, colors)
        table.add_row(Text(issue.key), bar)
    console.print(table)
    console.print(legend(colors))
    console.print()


def render_tickets_per_status(console: Console, report: Report, colors: dict[str, str]) -> None:
    """Print, for each status, the tickets that were in it and for how many hours."""
    summaries = {issue.key: issue.summary for issue in report.issues}
    table = Table(title="Tickets per status")
    table.add_column("Status")
    table.add_column("Ticket", no_wrap=True)
    table.add_column("Summary", max_width=SUMMARY_MAX_WIDTH, overflow="ellipsis", no_wrap=True)
    table.add_column("Hours", justify="right")
    for status in report.statuses:
        for index, key in enumerate(report.tickets_by_status[status]):
            label = Text(status, style=colors[status]) if index == 0 else ""
            hours = format_hours(report.hours_by_ticket[key][status])
            table.add_row(label, Text(key), Text(summaries[key]), hours)
        table.add_section()
    console.print(table)
    console.print()


def render_hours_matrix(console: Console, report: Report) -> None:
    """Print hours per ticket and status, with a total per ticket and per status."""
    totals = report.matrix_status_totals
    table = Table(title="Hours per status", show_footer=True)
    table.add_column("Ticket", footer="Total", no_wrap=True)
    table.add_column("Summary", max_width=SUMMARY_MAX_WIDTH, overflow="ellipsis", no_wrap=True)
    for status in report.statuses:
        table.add_column(Text(status), justify="right", footer=format_hours(totals[status]))
    table.add_column("Total h", justify="right", footer=format_hours(sum(totals.values())))
    for issue in report.issues:
        row = report.hours_by_ticket[issue.key]
        cells = [format_hours(row.get(status)) for status in report.statuses]
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
    available = console.width - LABEL_WIDTH - TABLE_CHROME_WIDTH
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
