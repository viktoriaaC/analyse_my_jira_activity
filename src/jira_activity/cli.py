"""Command line interface: parses options, connects the layers and turns errors into exit codes.

Exit codes: 0 = success, 1 = error shown as [JA-xxx], 2 = wrong usage, 130 = cancelled.
"""

from collections.abc import Callable
from datetime import datetime, timezone, tzinfo
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.text import Text

from jira_activity.adapters.credentials import configure as configure_credentials
from jira_activity.adapters.credentials import resolve_credentials
from jira_activity.adapters.jira_client import JiraClient, build_jql
from jira_activity.adapters.renderer import render_report
from jira_activity.domain.aggregate import IntervalsByIssue
from jira_activity.domain.models import DateRange, Issue, parse_day
from jira_activity.domain.timeline import build_intervals, clip
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
    run_safely(lambda: run_report(from_date, to_date, site, email, token, project, verbose))


@app.command(epilog=CONFIGURE_EPILOG)
def configure(
    site: Annotated[str, typer.Option(help="Jira site, e.g. https://acme.atlassian.net.")],
    email: Annotated[str, typer.Option(help="Email of your Atlassian account.")],
) -> None:
    """Save your Jira site, email and API token in the OS keychain, if you confirm."""
    run_safely(lambda: run_configure(site, email))


def run_report(
    from_date: str,
    to_date: str,
    site: str | None,
    email: str | None,
    token: str | None,
    project: str | None,
    verbose: bool,
) -> None:
    """Fetch the data for the period and print the report."""
    configure_logging(verbose)
    date_range = DateRange.from_dates(parse_day(from_date), parse_day(to_date), local_timezone())
    credentials = resolve_credentials(site, email, token)
    client = JiraClient(credentials.site, credentials.email, credentials.token)
    issues, intervals_by_issue = fetch_intervals(client, date_range, project, Console(stderr=True))
    render_report(Console(), issues, intervals_by_issue, date_range)


def run_configure(site: str, email: str) -> None:
    """Ask for the token, save if the user agrees and say what happened."""
    saved = configure_credentials(site, email)
    Console().print("Saved in the OS keychain." if saved else "Nothing was saved.")


def fetch_intervals(
    client: JiraClient,
    date_range: DateRange,
    project: str | None,
    status_console: Console,
) -> tuple[list[Issue], IntervalsByIssue]:
    """Fetch the user's tickets and turn each one's changelog into status intervals inside the range."""
    now = datetime.now(timezone.utc)
    with status_console.status("Searching for your tickets...") as status:
        issues = client.search_issues(build_jql(date_range, project))
        intervals_by_issue = {}
        for number, issue in enumerate(issues, start=1):
            status.update(f"Reading history of {issue.key} ({number}/{len(issues)})...")
            changes = client.fetch_status_changes(issue.key)
            intervals_by_issue[issue.key] = clip(build_intervals(issue, changes, now), date_range)
    return issues, intervals_by_issue


def local_timezone() -> tzinfo:
    """The timezone of this computer, used to decide where days start and end."""
    return datetime.now().astimezone().tzinfo


def run_safely(action: Callable[[], None]) -> None:
    """Run a command and turn every error into a message on stderr and an exit code."""
    try:
        action()
    except JiraActivityError as error:
        exit_with_error(str(error), EXIT_ERROR)
    except KeyboardInterrupt:
        exit_with_error("Cancelled.", EXIT_CANCELLED)
    except Exception as error:
        exit_with_error(str(JiraActivityError(type(error).__name__)), EXIT_ERROR)


def exit_with_error(message: str, exit_code: int) -> None:
    """Print the message in red on stderr and stop with the exit code."""
    Console(stderr=True).print(Text(message, style="bold red"))
    raise typer.Exit(exit_code)
