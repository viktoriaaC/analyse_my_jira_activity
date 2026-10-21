"""All errors the tool can raise, each with a unique code and message."""


class JiraActivityError(Exception):
    """Base class for every expected error. The CLI shows `[code] message`."""

    code = "JA-999"
    message = "An unexpected error occurred."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(str(self))

    def __str__(self) -> str:
        text = f"[{self.code}] {self.message}"
        return f"{text} ({self.detail})" if self.detail else text


# --- Jira API errors (JA-1xx) ---

class JiraAuthError(JiraActivityError):
    code = "JA-101"
    message = "Jira rejected the credentials (HTTP 401). Check your email and API token."


class JiraPermissionError(JiraActivityError):
    code = "JA-102"
    message = "You do not have permission to access this Jira resource (HTTP 403)."


class JiraNotFoundError(JiraActivityError):
    code = "JA-103"
    message = "Jira resource not found (HTTP 404). Check the site URL or issue key."


class JiraRateLimitError(JiraActivityError):
    code = "JA-104"
    message = "Jira rate limit still exceeded after retrying (HTTP 429). Try again later."


class JiraServerError(JiraActivityError):
    code = "JA-105"
    message = "Jira returned a server error (HTTP 5xx). Try again later."


class JiraConnectionError(JiraActivityError):
    code = "JA-106"
    message = "Could not connect to the Jira site. Check the URL and your network."


class JiraTimeoutError(JiraActivityError):
    code = "JA-107"
    message = "The request to Jira timed out."


class JiraResponseFormatError(JiraActivityError):
    code = "JA-108"
    message = "Jira returned a response in an unexpected format."


class JiraBadRequestError(JiraActivityError):
    code = "JA-109"
    message = "Jira rejected the request (HTTP 400). Check the project key and date range."


class JiraUnexpectedStatusError(JiraActivityError):
    code = "JA-110"
    message = "Jira answered with an unexpected HTTP status code."


class JiraSslError(JiraActivityError):
    code = "JA-111"
    message = "The Jira site's SSL certificate could not be verified. Check your VPN or company proxy."


class JiraRequestError(JiraActivityError):
    code = "JA-112"
    message = "The request to Jira could not be completed (for example too many redirects)."


# --- Input errors (JA-2xx) ---

class InvalidDateRangeError(JiraActivityError):
    code = "JA-201"
    message = "Invalid date range. Use YYYY-MM-DD and make sure --from is not after --to."


class InvalidSiteUrlError(JiraActivityError):
    code = "JA-202"
    message = "Invalid Jira site URL. Use the form https://<your-site>.atlassian.net."


# --- Credential errors (JA-3xx) ---

class CredentialStoreError(JiraActivityError):
    code = "JA-301"
    message = "Could not read from or write to the OS credential store."


class MissingCredentialsError(JiraActivityError):
    code = "JA-302"
    message = "No Jira credentials found. Pass them as options, set env vars or run `jira-activity configure`."


class EmptyCredentialError(JiraActivityError):
    code = "JA-303"
    message = "A required Jira credential was left empty at the prompt."


class CredentialStoreBackendError(JiraActivityError):
    code = "JA-304"
    message = "The OS keychain backend failed unexpectedly."


class PromptAbortedError(JiraActivityError):
    code = "JA-305"
    message = "Input ended before an answer was given (Ctrl+Z / Ctrl+D)."


# --- Output errors (JA-4xx) ---

class OutputWriteError(JiraActivityError):
    code = "JA-401"
    message = "The report could not be written to the output (closed pipe or unsupported characters)."
