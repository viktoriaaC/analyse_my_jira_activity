import keyring
import pytest
from typer.testing import CliRunner

from helpers import at, change, issue
from jira_activity import cli
from jira_activity.adapters.jira_client import JiraClient as RealJiraClient
from jira_activity.errors import JiraAuthError, OutputWriteError

runner = CliRunner()

CREDENTIAL_OPTIONS = ["--site", "https://acme.atlassian.net", "--email", "me@acme.se", "--token", "secret-token"]
PERIOD_OPTIONS = ["--from", "2026-10-01", "--to", "2026-10-04"]


class FakeClient:
    """Stands in for JiraClient; records what the CLI asked for."""

    instances = []
    error = None

    def __init__(self, site, email, token):
        self.site, self.email, self.token = site, email, token
        self.jql = None
        FakeClient.instances.append(self)

    def search_issues(self, jql):
        if FakeClient.error:
            raise FakeClient.error
        self.jql = jql
        return [issue(at(1), status="Done", key="ABC-1")]

    def fetch_status_changes(self, key):
        return [change(at(2), "To Do", "Done")]


@pytest.fixture(autouse=True)
def fake_jira(monkeypatch):
    FakeClient.instances = []
    FakeClient.error = None
    monkeypatch.setattr(cli, "JiraClient", FakeClient)
    for name in ["JIRA_SITE", "JIRA_EMAIL", "JIRA_API_TOKEN"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(keyring, "get_password", lambda service, name: None)


def run(*args):
    return runner.invoke(cli.app, list(args))


# --- help ---

def test_help_explains_getting_started():
    result = run("--help")
    assert result.exit_code == 0
    for text in ["report", "configure", "API token", "jira-activity report --from"]:
        assert text in result.stdout


def test_report_help_lists_every_option():
    result = run("report", "--help")
    assert result.exit_code == 0
    for option in ["--from", "--to", "--site", "--email", "--token", "--project", "--verbose"]:
        assert option in result.stdout
    assert "install-completion" not in result.stdout


def test_configure_help_lists_its_options():
    result = run("configure", "--help")
    assert "--site" in result.stdout and "--email" in result.stdout
    assert "--verbose" not in result.stdout


# --- report ---

def test_report_prints_all_sections():
    result = run("report", *PERIOD_OPTIONS, *CREDENTIAL_OPTIONS)
    assert result.exit_code == 0, result.stderr
    for title in ["Time per status", "Status timeline", "Tickets per status", "Hours per status"]:
        assert title in result.stdout
    assert "ABC-1" in result.stdout


def test_report_passes_credentials_and_project_to_jira():
    run("report", *PERIOD_OPTIONS, *CREDENTIAL_OPTIONS, "--project", "WEB")
    client = FakeClient.instances[0]
    assert (client.site, client.email, client.token) == ("https://acme.atlassian.net", "me@acme.se", "secret-token")
    assert 'project = "WEB"' in client.jql


def test_report_takes_credentials_from_env(monkeypatch):
    monkeypatch.setenv("JIRA_SITE", "https://env.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "env@acme.se")
    monkeypatch.setenv("JIRA_API_TOKEN", "env-token")
    result = run("report", *PERIOD_OPTIONS)
    assert result.exit_code == 0, result.stderr
    assert FakeClient.instances[0].token == "env-token"


def test_verbose_turns_on_debug_logging(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "configure_logging", calls.append)
    run("report", *PERIOD_OPTIONS, *CREDENTIAL_OPTIONS, "--verbose")
    run("report", *PERIOD_OPTIONS, *CREDENTIAL_OPTIONS)
    assert calls == [True, False]


def test_report_requires_from_and_to():
    result = run("report", *CREDENTIAL_OPTIONS)
    assert result.exit_code == 2


# --- errors ---

@pytest.mark.parametrize(
    "period",
    [["--from", "2026-10-05", "--to", "2026-10-01"], ["--from", "01/10/2026", "--to", "2026-10-04"]],
    ids=["from-after-to", "bad-format"],
)
def test_invalid_period_gives_ja_201(period):
    result = run("report", *period, *CREDENTIAL_OPTIONS)
    assert result.exit_code == 1
    assert "[JA-201]" in result.stderr
    assert FakeClient.instances == []


def test_jira_error_is_shown_with_code_and_exit_1():
    FakeClient.error = JiraAuthError()
    result = run("report", *PERIOD_OPTIONS, *CREDENTIAL_OPTIONS)
    assert result.exit_code == 1
    assert "[JA-101]" in result.stderr
    assert "secret-token" not in result.stdout + result.stderr


def test_missing_credentials_without_terminal_gives_ja_302():
    result = run("report", *PERIOD_OPTIONS)
    assert result.exit_code == 1
    assert "[JA-302]" in result.stderr


def test_invalid_site_gives_ja_202(monkeypatch):
    monkeypatch.setattr(cli, "JiraClient", RealJiraClient)
    result = run("report", *PERIOD_OPTIONS, "--site", "http://acme", "--email", "me@acme.se", "--token", "t")
    assert result.exit_code == 1
    assert "[JA-202]" in result.stderr


def test_credentials_are_never_sent_to_a_non_jira_host():
    result = run("report", *PERIOD_OPTIONS, "--site", "https://acme.atlassian.net@evil.example",
                 "--email", "me@acme.se", "--token", "secret-token")
    assert result.exit_code == 1
    assert "[JA-202]" in result.stderr
    assert FakeClient.instances == []


def test_too_long_period_gives_ja_204():
    result = run("report", "--from", "2025-01-01", "--to", "2026-10-01", *CREDENTIAL_OPTIONS)
    assert result.exit_code == 1
    assert "[JA-204]" in result.stderr
    assert FakeClient.instances == []


def test_unexpected_error_gives_ja_999():
    FakeClient.error = ZeroDivisionError("boom")
    result = run("report", *PERIOD_OPTIONS, *CREDENTIAL_OPTIONS)
    assert result.exit_code == 1
    assert "[JA-999]" in result.stderr
    assert "ZeroDivisionError" in result.stderr


def test_output_failure_gives_ja_401(monkeypatch):
    def broken_output(report):
        raise OutputWriteError("BrokenPipeError")
    monkeypatch.setattr(cli, "print_report", broken_output)
    result = run("report", *PERIOD_OPTIONS, *CREDENTIAL_OPTIONS)
    assert result.exit_code == 1
    assert "[JA-401]" in result.stderr


def test_ctrl_c_exits_130():
    FakeClient.error = KeyboardInterrupt()
    result = run("report", *PERIOD_OPTIONS, *CREDENTIAL_OPTIONS)
    assert result.exit_code == 130
    assert "Cancelled." in result.stderr


# --- configure ---

@pytest.mark.parametrize("saved, message", [(True, "Saved in the OS keychain."), (False, "Nothing was saved.")])
def test_configure_reports_whether_it_saved(monkeypatch, saved, message):
    calls = []
    monkeypatch.setattr(cli, "configure_credentials", lambda site, email: calls.append((site, email)) or saved)
    result = run("configure", "--site", "https://acme.atlassian.net", "--email", "me@acme.se")
    assert result.exit_code == 0
    assert message in result.stdout
    assert calls == [("https://acme.atlassian.net", "me@acme.se")]


def test_configure_requires_site_and_email():
    assert run("configure", "--site", "https://acme.atlassian.net").exit_code == 2


def test_configure_without_terminal_gives_ja_302():
    result = run("configure", "--site", "https://acme.atlassian.net", "--email", "me@acme.se")
    assert result.exit_code == 1
    assert "[JA-302]" in result.stderr
