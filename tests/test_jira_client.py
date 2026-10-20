import pytest
import requests

from helpers import at, change, date_range
from jira_activity.adapters.jira_client import JiraClient, build_jql, validate_site_url
from jira_activity.domain.models import Issue

SITE = "https://acme.atlassian.net"


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, invalid_json=False):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self._invalid_json = invalid_json

    def json(self):
        if self._invalid_json:
            raise ValueError("not json")
        return self._body


class FakeSession:
    """Returns queued responses (or raises queued exceptions) and records each call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}
        self.auth = None

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_client(*responses):
    session = FakeSession(*responses)
    sleeps = []
    client = JiraClient(SITE, "me@acme.se", "secret-token", session=session, sleep=sleeps.append)
    return client, session, sleeps


def raw_issue(key="ABC-1", status="To Do", created="2026-10-01T10:00:00.000+0000"):
    return {"key": key, "fields": {"summary": f"Summary {key}", "status": {"name": status}, "created": created}}


def changelog_entry(created, *items):
    return {"created": created, "items": list(items)}


def status_item(from_status, to_status):
    return {"field": "status", "fromString": from_status, "toString": to_status}


# --- site URL and JQL ---

def test_validate_site_url_strips_path_and_trailing_slash():
    assert validate_site_url(" https://acme.atlassian.net/jira/ ") == SITE


@pytest.mark.parametrize("site", ["http://acme.atlassian.net", "acme.atlassian.net", "https://", ""])
def test_validate_site_url_rejects_non_https(site):
    with pytest.raises(Exception) as error:
        validate_site_url(site)
    assert error.value.code == "JA-202"


def test_build_jql_searches_with_a_day_of_margin():
    jql = build_jql(date_range(at(2), at(5)))
    assert jql == 'assignee was currentUser() DURING ("2026-10-01 00:00", "2026-10-06 00:00") ORDER BY key ASC'


def test_build_jql_quotes_project_key():
    jql = build_jql(date_range(at(2), at(5)), project='AB" OR x = "y')
    assert 'AND project = "AB\\" OR x = \\"y"' in jql


# --- client setup ---

def test_client_uses_basic_auth_and_json_accept_header():
    _, session, _ = make_client()
    assert session.auth == ("me@acme.se", "secret-token")
    assert session.headers["Accept"] == "application/json"


# --- search ---

def test_search_issues_parses_issues():
    client, session, _ = make_client(FakeResponse(body={"issues": [raw_issue()], "isLast": True}))
    issues = client.search_issues("some jql")
    assert issues == [Issue("ABC-1", "Summary ABC-1", "To Do", at(1, 10))]
    call = session.calls[0]
    assert call["url"] == SITE + "/rest/api/3/search/jql"
    assert call["params"]["jql"] == "some jql"
    assert call["params"]["fields"] == "summary,status,created"
    assert call["timeout"] == 30


def test_search_issues_follows_next_page_token():
    client, session, _ = make_client(
        FakeResponse(body={"issues": [raw_issue("ABC-1")], "nextPageToken": "page2", "isLast": False}),
        FakeResponse(body={"issues": [raw_issue("ABC-2")], "isLast": True}),
    )
    issues = client.search_issues("jql")
    assert [issue.key for issue in issues] == ["ABC-1", "ABC-2"]
    assert "nextPageToken" not in session.calls[0]["params"]
    assert session.calls[1]["params"]["nextPageToken"] == "page2"


def test_search_issues_parses_timezone_offsets():
    client, _, _ = make_client(
        FakeResponse(body={"issues": [raw_issue(created="2026-10-01T12:00:00.000+0200")], "isLast": True})
    )
    assert client.search_issues("jql")[0].created == at(1, 10)


# --- changelog ---

def test_fetch_status_changes_keeps_only_status_items():
    body = {
        "values": [
            changelog_entry(
                "2026-10-02T00:00:00.000+0000",
                {"field": "assignee", "fromString": "A", "toString": "B"},
                status_item("To Do", "In Progress"),
            )
        ],
        "isLast": True,
    }
    client, session, _ = make_client(FakeResponse(body=body))
    assert client.fetch_status_changes("ABC-1") == [change(at(2), "To Do", "In Progress")]
    assert session.calls[0]["url"] == SITE + "/rest/api/3/issue/ABC-1/changelog"


def test_fetch_status_changes_follows_pages_and_sorts():
    client, session, _ = make_client(
        FakeResponse(body={
            "values": [changelog_entry("2026-10-04T00:00:00.000+0000", status_item("In Progress", "Done"))],
            "startAt": 0, "total": 2, "isLast": False,
        }),
        FakeResponse(body={
            "values": [changelog_entry("2026-10-02T00:00:00.000+0000", status_item("To Do", "In Progress"))],
            "startAt": 1, "total": 2, "isLast": True,
        }),
    )
    changes = client.fetch_status_changes("ABC-1")
    assert changes == [change(at(2), "To Do", "In Progress"), change(at(4), "In Progress", "Done")]
    assert session.calls[1]["params"]["startAt"] == 1


def test_fetch_status_changes_stops_on_empty_page():
    client, session, _ = make_client(FakeResponse(body={"values": [], "isLast": False}))
    assert client.fetch_status_changes("ABC-1") == []
    assert len(session.calls) == 1


# --- HTTP errors ---

@pytest.mark.parametrize(
    "status, code",
    [(400, "JA-109"), (401, "JA-101"), (403, "JA-102"), (404, "JA-103"),
     (500, "JA-105"), (503, "JA-105"), (418, "JA-110")],
)
def test_http_status_maps_to_error_code(status, code):
    client, _, _ = make_client(FakeResponse(status_code=status, invalid_json=True))
    with pytest.raises(Exception) as error:
        client.search_issues("jql")
    assert error.value.code == code


def test_bad_request_includes_jira_error_messages():
    body = {"errorMessages": ["The value 'XYZ' does not exist for the field 'project'."], "errors": {}}
    client, _, _ = make_client(FakeResponse(status_code=400, body=body))
    with pytest.raises(Exception) as error:
        client.search_issues("jql")
    assert "XYZ" in str(error.value)


def test_error_message_never_contains_token():
    client, _, _ = make_client(FakeResponse(status_code=401, invalid_json=True))
    with pytest.raises(Exception) as error:
        client.search_issues("jql")
    assert "secret-token" not in str(error.value)


# --- rate limiting ---

def test_rate_limit_is_retried_using_retry_after():
    ok = FakeResponse(body={"issues": [], "isLast": True})
    client, session, sleeps = make_client(FakeResponse(429, headers={"Retry-After": "5"}), ok)
    assert client.search_issues("jql") == []
    assert sleeps == [5.0]
    assert len(session.calls) == 2


def test_rate_limit_without_retry_after_backs_off_exponentially():
    responses = [FakeResponse(429)] * 3 + [FakeResponse(body={"issues": [], "isLast": True})]
    client, _, sleeps = make_client(*responses)
    client.search_issues("jql")
    assert sleeps == [1.0, 2.0, 4.0]


def test_rate_limit_gives_up_after_max_retries():
    client, session, sleeps = make_client(*[FakeResponse(429)] * 4)
    with pytest.raises(Exception) as error:
        client.search_issues("jql")
    assert error.value.code == "JA-104"
    assert len(session.calls) == 4
    assert len(sleeps) == 3


def test_retry_after_is_capped():
    ok = FakeResponse(body={"issues": [], "isLast": True})
    client, _, sleeps = make_client(FakeResponse(429, headers={"Retry-After": "3600"}), ok)
    client.search_issues("jql")
    assert sleeps == [60.0]


# --- network errors ---

@pytest.mark.parametrize(
    "exception, code",
    [
        (requests.ConnectionError("down"), "JA-106"),
        (requests.exceptions.SSLError("bad cert"), "JA-106"),
        (requests.Timeout("slow"), "JA-107"),
        (requests.exceptions.ConnectTimeout("slow connect"), "JA-107"),
        (requests.exceptions.TooManyRedirects("loop"), "JA-106"),
    ],
)
def test_network_errors_map_to_error_code(exception, code):
    client, _, _ = make_client(exception)
    with pytest.raises(Exception) as error:
        client.search_issues("jql")
    assert error.value.code == code


# --- response format errors ---

@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(invalid_json=True),
        FakeResponse(body=["not", "an", "object"]),
        FakeResponse(body={"isLast": True}),
        FakeResponse(body={"issues": [{"key": "ABC-1"}], "isLast": True}),
        FakeResponse(body={"issues": [raw_issue(created="yesterday")], "isLast": True}),
    ],
    ids=["invalid-json", "not-object", "missing-issues", "missing-fields", "bad-timestamp"],
)
def test_unexpected_response_format_raises(response):
    client, _, _ = make_client(response)
    with pytest.raises(Exception) as error:
        client.search_issues("jql")
    assert error.value.code == "JA-108"
