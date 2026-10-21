"""All HTTP communication with the Jira Cloud REST API (v3)."""

import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import requests

from jira_activity.domain.models import DateRange, Issue, StatusChange
from jira_activity.errors import (
    InvalidSiteUrlError,
    JiraAuthError,
    JiraBadRequestError,
    JiraConnectionError,
    JiraNotFoundError,
    JiraPermissionError,
    JiraRateLimitError,
    JiraRequestError,
    JiraResponseFormatError,
    JiraServerError,
    JiraSslError,
    JiraTimeoutError,
    JiraUnexpectedStatusError,
)
from jira_activity.utils.logger import log_request

SEARCH_PATH = "/rest/api/3/search/jql"
CHANGELOG_PATH = "/rest/api/3/issue/{key}/changelog"
SEARCH_FIELDS = "summary,status,created"
PAGE_SIZE = 100
TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
MAX_RETRY_DELAY_SECONDS = 60
JIRA_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
JQL_DATETIME_FORMAT = "%Y-%m-%d %H:%M"
# JQL dates are read in the Jira user's profile timezone, which may differ from
# the local one. Searching one extra day each side means no ticket is missed;
# clipping later removes any time outside the real range.
SEARCH_MARGIN = timedelta(days=1)

_ERRORS_BY_STATUS = {
    400: JiraBadRequestError,
    401: JiraAuthError,
    403: JiraPermissionError,
    404: JiraNotFoundError,
}


def validate_site_url(site: str) -> str:
    """Return the site URL without a trailing slash, or raise if it is not an https URL."""
    parts = urlsplit(site.strip())
    if parts.scheme != "https" or not parts.hostname:
        raise InvalidSiteUrlError(site)
    return f"https://{parts.netloc}"


def build_jql(date_range: DateRange, project: str | None = None) -> str:
    """Build the JQL for tickets assigned to the current user at some point in the range."""
    start = (date_range.start - SEARCH_MARGIN).strftime(JQL_DATETIME_FORMAT)
    end = (date_range.end + SEARCH_MARGIN).strftime(JQL_DATETIME_FORMAT)
    jql = f'assignee was currentUser() DURING ("{start}", "{end}")'
    if project:
        jql += f" AND project = {_quote_jql(project)}"
    return jql + " ORDER BY key ASC"


def _quote_jql(value: str) -> str:
    """Quote a value so it is always read as one literal in JQL."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class JiraClient:
    """Reads issues and status changes from one Jira Cloud site."""

    def __init__(
        self,
        site: str,
        email: str,
        token: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = validate_site_url(site)
        self._session = session or requests.Session()
        self._session.auth = (email, token)
        self._session.headers.update({"Accept": "application/json"})
        self._sleep = sleep

    def search_issues(self, jql: str) -> list[Issue]:
        """Return every issue matching the JQL, following all result pages."""
        return [_parse_issue(raw) for raw in self._search_pages(jql)]

    def fetch_status_changes(self, key: str) -> list[StatusChange]:
        """Return every status change in the issue's changelog, oldest first."""
        changes = [
            change
            for entry in self._changelog_pages(key)
            for change in _parse_status_changes(entry)
        ]
        return sorted(changes, key=lambda change: change.at)

    def _search_pages(self, jql: str) -> Iterator[dict]:
        """Yield raw issues page by page using nextPageToken."""
        params = {"jql": jql, "fields": SEARCH_FIELDS, "maxResults": PAGE_SIZE}
        while True:
            page = self._get(SEARCH_PATH, params)
            yield from _required(page, "issues")
            token = page.get("nextPageToken")
            if page.get("isLast", True) or not token:
                return
            params = {**params, "nextPageToken": token}

    def _changelog_pages(self, key: str) -> Iterator[dict]:
        """Yield raw changelog entries page by page using startAt."""
        path = CHANGELOG_PATH.format(key=key)
        start_at = 0
        while True:
            page = self._get(path, {"startAt": start_at, "maxResults": PAGE_SIZE})
            values = _required(page, "values")
            yield from values
            start_at += len(values)
            if not values or page.get("isLast", start_at >= page.get("total", 0)):
                return

    def _get(self, path: str, params: dict) -> dict:
        """GET a Jira endpoint and return the JSON body."""
        response = self._send_with_retries(self._base_url + path, params)
        _raise_for_status(response)
        return _parse_json(response)

    def _send_with_retries(self, url: str, params: dict) -> requests.Response:
        """Send the request, waiting and retrying while Jira answers 429 (rate limited)."""
        for attempt in range(MAX_RETRIES):
            response = self._send(url, params)
            if response.status_code != 429:
                return response
            self._sleep(_retry_delay(response, attempt))
        response = self._send(url, params)
        if response.status_code == 429:
            raise JiraRateLimitError(f"gave up after {MAX_RETRIES} retries")
        return response

    def _send(self, url: str, params: dict) -> requests.Response:
        """Send one GET request, log it, and turn network failures into tool errors."""
        try:
            response = self._session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except requests.Timeout as error:
            raise JiraTimeoutError(f"no answer within {TIMEOUT_SECONDS} s") from error
        except requests.exceptions.SSLError as error:
            raise JiraSslError(urlsplit(url).netloc) from error
        except requests.ConnectionError as error:
            raise JiraConnectionError(urlsplit(url).netloc) from error
        except requests.RequestException as error:
            raise JiraRequestError(type(error).__name__) from error
        log_request("GET", url, response.status_code)
        return response


def _raise_for_status(response: requests.Response) -> None:
    """Raise the tool error that matches a non-2xx status code."""
    status = response.status_code
    if 200 <= status < 300:
        return
    if status in _ERRORS_BY_STATUS:
        raise _ERRORS_BY_STATUS[status](_jira_error_messages(response))
    if status >= 500:
        raise JiraServerError(f"HTTP {status}")
    raise JiraUnexpectedStatusError(f"HTTP {status}")


def _jira_error_messages(response: requests.Response) -> str | None:
    """Return Jira's own error messages from an error response, if it has any."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    messages = list(body.get("errorMessages") or []) + list((body.get("errors") or {}).values())
    return "; ".join(str(message) for message in messages) or None


def _retry_delay(response: requests.Response, attempt: int) -> float:
    """Return seconds to wait before retrying: Retry-After if given, else exponential backoff."""
    try:
        delay = float(response.headers.get("Retry-After", ""))
    except ValueError:
        delay = 2.0 ** attempt
    return min(max(delay, 0.0), MAX_RETRY_DELAY_SECONDS)


def _parse_json(response: requests.Response) -> dict:
    """Return the response body as a JSON object."""
    try:
        body = response.json()
    except ValueError as error:
        raise JiraResponseFormatError("body is not valid JSON") from error
    if not isinstance(body, dict):
        raise JiraResponseFormatError("body is not a JSON object")
    return body


def _required(data: dict, key: str):
    """Return data[key], or raise if Jira left it out."""
    try:
        return data[key]
    except (KeyError, TypeError) as error:
        raise JiraResponseFormatError(f"missing '{key}'") from error


def _parse_issue(raw: dict) -> Issue:
    """Build an Issue from one entry of the search response."""
    fields = _required(raw, "fields")
    return Issue(
        key=_required(raw, "key"),
        summary=_required(fields, "summary"),
        status=_required(_required(fields, "status"), "name"),
        created=_parse_datetime(_required(fields, "created")),
    )


def _parse_status_changes(entry: dict) -> list[StatusChange]:
    """Return the status changes in one changelog entry, ignoring other fields."""
    at = _parse_datetime(_required(entry, "created"))
    return [
        StatusChange(at=at, from_status=_required(item, "fromString"), to_status=_required(item, "toString"))
        for item in _required(entry, "items")
        if item.get("field") == "status"
    ]


def _parse_datetime(value: str) -> datetime:
    """Parse a Jira timestamp such as 2026-10-01T10:00:00.000+0200."""
    try:
        return datetime.strptime(value, JIRA_DATETIME_FORMAT)
    except (TypeError, ValueError) as error:
        raise JiraResponseFormatError(f"bad timestamp {value!r}") from error
