from rich.console import Console

from helpers import at, date_range, interval, issue
from jira_activity.adapters.renderer import (
    BAR,
    GAP,
    STATUS_COLORS,
    assign_colors,
    date_axis,
    format_hours,
    render_report,
    timeline_bar,
    timeline_width,
)
from jira_activity.domain.models import Issue
from jira_activity.domain.report import build_report

PERIOD = date_range(at(1), at(5))  # 2026-10-01 .. 2026-10-04, 96 hours

ISSUES = [
    issue(at(1), key="ABC-1"),
    issue(at(1), key="ABC-2"),
]
INTERVALS = {
    "ABC-1": [interval("To Do", at(1), at(2)), interval("In Progress", at(2), at(5))],
    "ABC-2": [interval("To Do", at(3), at(5))],
}


def recording_console(width=140):
    return Console(record=True, width=width, color_system=None, force_terminal=False)


def report_text(issues=ISSUES, intervals=INTERVALS):
    console = recording_console()
    render_report(console, build_report(issues, intervals, PERIOD))
    return console.export_text()


def line_with(text, *needles):
    return next(line for line in text.splitlines() if all(needle in line for needle in needles))


# --- whole report ---

def test_title_shows_period_and_ticket_count():
    text = report_text()
    assert "Jira activity 2026-10-01 – 2026-10-04" in text
    assert "2 ticket(s)" in text


def test_report_contains_all_four_sections():
    text = report_text()
    for title in ["Time per status", "Status timeline", "Tickets per status", "Hours per status"]:
        assert title in text


def test_empty_report_shows_message_only():
    text = report_text(issues=ISSUES, intervals={"ABC-1": [], "ABC-2": []})
    assert "No tickets were assigned to you in this period." in text
    assert "Hours per status" not in text


def test_summary_shows_hours_and_ticket_count_per_status():
    text = report_text()
    to_do = line_with(text, "To Do", "72.0")
    assert "2" in to_do.split("72.0")[1]
    assert "72.0" in line_with(text, "In Progress", "72.0")


def test_hours_matrix_row_has_dash_for_unused_status_and_total():
    text = report_text()
    row = line_with(text, "ABC-2", "A ticket", "–")
    assert "48.0" in row
    full_row = line_with(text, "ABC-1", "24.0", "72.0", "96.0")
    assert full_row


def test_hours_matrix_footer_totals_each_status():
    text = report_text()
    footer = line_with(text, "Total", "144.0")
    assert "72.0" in footer


def test_tickets_per_status_lists_tickets_under_their_status():
    section = report_text().split("Tickets per status")[1].split("Hours per status")[0]
    assert line_with(section, "To Do", "ABC-1", "24.0")
    assert line_with(section, "ABC-2", "48.0")
    assert line_with(section, "In Progress", "ABC-1", "72.0")


def test_tickets_without_intervals_are_left_out():
    text = report_text(intervals={"ABC-1": INTERVALS["ABC-1"], "ABC-2": []})
    assert "1 ticket(s)" in text
    assert "ABC-2" not in text


def test_square_brackets_in_jira_data_are_printed_as_is():
    tricky = [Issue("[X]-1", "[UI] Fix [bold]button[/bold]", "[Blocked]", at(1))]
    text = report_text(issues=tricky, intervals={"[X]-1": [interval("[Blocked]", at(1), at(2))]})
    assert line_with(text, "[X]-1", "[UI] Fix [bold]button[/bold]")
    assert line_with(text, "Ticket", "Summary", "[Blocked]", "Total h")


# --- timeline pieces ---

def test_timeline_bar_draws_one_slot_per_day():
    colors = assign_colors(["To Do", "In Progress"])
    bar = timeline_bar(INTERVALS["ABC-2"], PERIOD, 4, colors)
    assert bar.plain == GAP * 2 + BAR * 2


def test_timeline_bar_colours_slots_by_status():
    colors = assign_colors(["To Do", "In Progress"])
    bar = timeline_bar(INTERVALS["ABC-1"], PERIOD, 4, colors)
    styles = [str(span.style) for span in bar.spans]
    assert styles == [colors["To Do"]] + [colors["In Progress"]] * 3


def test_date_axis_puts_dates_at_both_ends():
    axis = date_axis(PERIOD, 30)
    assert len(axis) == 30
    assert axis.startswith("2026-10-01") and axis.endswith("2026-10-04")


def test_timeline_width_is_clamped():
    assert timeline_width(recording_console(width=20)) == 20
    assert timeline_width(recording_console(width=400)) == 100


def test_legend_lists_every_status():
    text = report_text()
    legend_line = line_with(text, "Legend:")
    assert "To Do" in legend_line and "In Progress" in legend_line


# --- small helpers ---

def test_colours_cycle_when_statuses_outnumber_them():
    statuses = [f"S{index}" for index in range(len(STATUS_COLORS) + 1)]
    colors = assign_colors(statuses)
    assert colors[statuses[-1]] == colors[statuses[0]]
    assert len(set(colors[s] for s in statuses[:-1])) == len(STATUS_COLORS)


def test_format_hours():
    assert format_hours(None) == "–"
    assert format_hours(4) == "4.0"
    assert format_hours(1.26) == "1.3"
