"""Command line interface: parses options, connects the layers and turns errors into exit codes.

This module does no I/O itself: terminal output goes through adapters.terminal,
the clock through adapters.clock and Jira through adapters.jira_client.

Exit codes: 0 = success, 1 = error shown as [JA-xxx], 2 = wrong usage, 130 = cancelled.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Optional

import typer

from jira_activity.adapters.clock import local_timezone, now_utc
from jira_activity.adapters.credentials import ask_and_save_credentials, resolve_credentials
from jira_activity.adapters.jira_client import JiraClient, build_jql
from jira_activity.adapters.terminal import print_error, print_message, print_report, progress
from jira_activity.domain.models import DateRange, Issue, StatusChange, parse_day
from jira_activity.domain.report import build_report
from jira_activity.domain.timeline import intervals_in_range
from jira_activity.errors import JiraActivityError
from jira_activity.utils.logger import configure_logging

EXIT_ERROR = 1
EXIT_CANCELLED = 130

APP_HELP = """
Show which statuses your Jira Cloud tickets were in during a period, and for how many hours.

Tickets count as yours if they were assigned to you at some point in the period.

Getting started:

  1. Create an API token at https://id.atlassian.com/manage-profile/security/api-tokens

  2. jira-activity configure --site https://acme.atlassian.net --email me@acme.se

  3. jira-activity report --from 2026-09-01 --to 2026-09-30
"""

REPORT_EPILOG = """
Credentials are taken from the first place that has them: option, environment variable
(JIRA_SITE, JIRA_EMAIL, JIRA_API_TOKEN), OS keychain (see `configure`), or a prompt.


Examples:

  jira-activity report --from 2026-09-01 --to 2026-09-30

  jira-activity report --from 2026-09-01 --to 2026-09-07 --project WEB --verbose
"""

CONFIGURE_EPILOG = """
You are asked for the API token (hidden input) and then whether to save.
Nothing is saved unless you answer yes, and nothing is written to a plain file.
"""

app = typer.Typer(help=APP_HELP, no_args_is_help=True, add_completion=False)


@app.command(epilog=REPORT_EPILOG)
def report(
    from_date: Annotated[str, typer.Option("--from", help="First day of the period, YYYY-MM-DD.")],
    to_date: Annotated[str, typer.Option("--to", help="Last day of the period (included), YYYY-MM-DD.")],
    site: Annotated[Optional[str], typer.Option(help="Jira site, e.g. https://acme.atlassian.net.")] = None,
    email: Annotated[Optional[str], typer.Option(help="Email of your Atlassian account.")] = None,
    token: Annotated[
        Optional[str],
        typer.Option(help="Jira API token. Prefer JIRA_API_TOKEN or the keychain: options end up in shell history."),
    ] = None,
    project: Annotated[Optional[str], typer.Option(help="Only include tickets in this project, e.g. WEB.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Log each Jira request (method, path, status) to stderr.")] = False,
) -> None:
    """Show the statuses of your tickets during a period: summary, timeline and hours per status."""
    options = ReportOptions(
        from_date=from_date,
        to_date=to_date,
        site=site,
        email=email,
        token=token,
        project=project,
        verbose=verbose,
    )
    run_safely(run_report, options)


@app.command(epilog=CONFIGURE_EPILOG)
def configure(
    site: Annotated[str, typer.Option(help="Jira site, e.g. https://acme.atlassian.net.")],
    email: Annotated[str, typer.Option(help="Email of your Atlassian account.")],
) -> None:
    """Save your Jira site, email and API token in the OS keychain, if you confirm."""
    run_safely(run_configure, site, email)


@dataclass(frozen=True)
class ReportOptions:
    """The options of `report`, by name, so values of the same type cannot be swapped by position."""

    from_date: str
    to_date: str
    site: str | None
    email: str | None
    token: str | None = field(repr=False)
    project: str | None
    verbose: bool


def run_report(options: ReportOptions) -> None:
    """Run the report command: prepare, fetch from Jira, then print."""
    configure_logging(options.verbose)
    date_range = parse_period(options.from_date, options.to_date)
    client = connect_to_jira(options)
    issues, changes_by_key = fetch_jira_data(client, date_range, options.project)
    intervals_by_issue = intervals_in_range(issues, changes_by_key, date_range, now_utc())
    print_report(build_report(issues, intervals_by_issue, date_range))


def run_configure(site: str, email: str) -> None:
    """Ask for the token, save if the user agrees and say what happened."""
    saved = ask_and_save_credentials(site, email)
    print_message("Saved in the OS keychain." if saved else "Nothing was saved.")


def parse_period(from_date: str, to_date: str) -> DateRange:
    """Turn the --from and --to options into a date range in this computer's timezone."""
    return DateRange.from_dates(parse_day(from_date), parse_day(to_date), local_timezone())


def connect_to_jira(options: ReportOptions) -> JiraClient:
    """Find the credentials and create a Jira client with them."""
    credentials = resolve_credentials(options.site, options.email, options.token)
    return JiraClient(credentials.site, credentials.email, credentials.token)


def fetch_jira_data(
    client: JiraClient,
    date_range: DateRange,
    project: str | None,
) -> tuple[list[Issue], dict[str, list[StatusChange]]]:
    """Fetch the user's tickets in the range and each ticket's status changes, showing progress."""
    with progress("Searching for your tickets...") as show_progress:
        issues = client.search_issues(build_jql(date_range, project))
        changes_by_key = fetch_status_changes_by_key(client, issues, show_progress)
    return issues, changes_by_key


def fetch_status_changes_by_key(
    client: JiraClient,
    issues: list[Issue],
    show_progress: Callable[[str], None],
) -> dict[str, list[StatusChange]]:
    """Read each issue's status changes from Jira, reporting progress as it goes."""
    changes_by_key = {}
    for number, issue in enumerate(issues, start=1):
        show_progress(f"Reading history of {issue.key} ({number}/{len(issues)})...")
        changes_by_key[issue.key] = client.fetch_status_changes(issue.key)
    return changes_by_key


def run_safely(action: Callable[..., None], *args: object) -> None:
    """Run action(*args) and turn every error into a message on stderr and an exit code."""
    try:
        action(*args)
    except JiraActivityError as error:
        exit_with_error(str(error), EXIT_ERROR)
    except KeyboardInterrupt:
        exit_with_error("Cancelled.", EXIT_CANCELLED)
    except Exception as error:
        exit_with_error(str(JiraActivityError(type(error).__name__)), EXIT_ERROR)


def exit_with_error(message: str, exit_code: int) -> None:
    """Show the message on stderr and stop with the exit code."""
    print_error(message)
    raise typer.Exit(exit_code)
