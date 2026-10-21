"""Validation of user input: the Jira site URL and the account email.

Error details never repeat a username or password that was typed into a URL.
"""

import re
from urllib.parse import SplitResult, urlsplit

from jira_activity.errors import InvalidEmailError, InvalidSiteUrlError

# One DNS label in front of atlassian.net, as Jira Cloud sites use: acme.atlassian.net
JIRA_CLOUD_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.atlassian\.net$")
HTTPS_PORT = 443
# Deliberately simple: one @, no spaces, a dot in the domain part.
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_site_url(site: str) -> str:
    """Return the site as https://<site>.atlassian.net, or raise if it is anything else.

    Credentials are sent to this host, so anything that could point them elsewhere is rejected:
    other schemes, other hosts, a username or password in the URL, and non-standard ports.
    """
    parts = urlsplit(site.strip())
    reason = _site_problem(parts)
    if reason:
        raise InvalidSiteUrlError(f"{reason}: {_redacted(parts)}")
    return f"https://{parts.hostname}"


def validate_email(email: str) -> str:
    """Return the email without surrounding spaces, or raise if it does not look like an email address."""
    email = email.strip()
    if not EMAIL.match(email):
        raise InvalidEmailError(f"'{email}' is not an email address")
    return email


def _site_problem(parts: SplitResult) -> str | None:
    """Return why the URL is not an acceptable Jira Cloud site, or None if it is fine."""
    if parts.scheme != "https":
        return "must start with https://"
    if parts.username is not None or parts.password is not None:
        return "must not contain a username or password"
    if not parts.hostname or not JIRA_CLOUD_HOST.match(parts.hostname):
        return "must be a <your-site>.atlassian.net address"
    if _port(parts) not in (None, HTTPS_PORT):
        return "must not use a custom port"
    return None


def _port(parts: SplitResult) -> int | None:
    """Return the port in the URL, or -1 if it is not a valid number."""
    try:
        return parts.port
    except ValueError:
        return -1


def _redacted(parts: SplitResult) -> str:
    """Show the URL as scheme and host only, so a typed username or password is never printed."""
    if parts.hostname:
        return f"{parts.scheme or '?'}://{parts.hostname}"
    return "the value given"
