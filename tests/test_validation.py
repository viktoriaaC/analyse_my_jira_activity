import pytest

from jira_activity.domain.validation import validate_email, validate_site_url
from jira_activity.errors import InvalidEmailError, InvalidSiteUrlError

SITE = "https://acme.atlassian.net"


# --- site URL ---

@pytest.mark.parametrize(
    "site",
    [
        "https://acme.atlassian.net",
        " https://acme.atlassian.net/jira/ ",
        "https://ACME.Atlassian.net",
        "https://acme.atlassian.net:443",
        "https://acme.atlassian.net/?x=1#top",
    ],
)
def test_valid_site_is_normalised_to_scheme_and_host(site):
    assert validate_site_url(site) == SITE


def test_site_with_hyphen_and_digits_is_accepted():
    assert validate_site_url("https://my-team-2.atlassian.net") == "https://my-team-2.atlassian.net"


@pytest.mark.parametrize(
    "site, reason",
    [
        ("http://acme.atlassian.net", "must start with https://"),
        ("acme.atlassian.net", "must start with https://"),
        ("", "must start with https://"),
        ("https://", "must be a <your-site>.atlassian.net address"),
        ("https://evil.example", "must be a <your-site>.atlassian.net address"),
        ("https://acme.atlassian.net.evil.example", "must be a <your-site>.atlassian.net address"),
        ("https://atlassian.net", "must be a <your-site>.atlassian.net address"),
        ("https://a.b.atlassian.net", "must be a <your-site>.atlassian.net address"),
        ("https://-acme.atlassian.net", "must be a <your-site>.atlassian.net address"),
        ("https://acme.atlassian.net@evil.example", "must not contain a username or password"),
        ("https://user:secret@acme.atlassian.net", "must not contain a username or password"),
        ("https://acme.atlassian.net:8443", "must not use a custom port"),
        ("https://acme.atlassian.net:abc", "must not use a custom port"),
    ],
)
def test_invalid_site_is_rejected_with_its_reason(site, reason):
    with pytest.raises(InvalidSiteUrlError) as error:
        validate_site_url(site)
    assert error.value.code == "JA-202"
    assert reason in str(error.value)


@pytest.mark.parametrize(
    "site",
    [
        "https://alice:hunter2@acme.atlassian.net",
        "http://alice:hunter2@acme.atlassian.net",
        "https://hunter2@evil.example",
    ],
)
def test_username_and_password_are_never_shown_in_the_error(site):
    with pytest.raises(InvalidSiteUrlError) as error:
        validate_site_url(site)
    assert "hunter2" not in str(error.value)
    assert "alice" not in str(error.value)


# --- email ---

@pytest.mark.parametrize("email", ["me@acme.se", " first.last+jira@sub.acme.co.uk "])
def test_valid_email_is_returned_trimmed(email):
    assert validate_email(email) == email.strip()


@pytest.mark.parametrize("email", ["", "me", "me@", "@acme.se", "me@acme", "me @acme.se", "a@b@c.se"])
def test_invalid_email_is_rejected(email):
    with pytest.raises(InvalidEmailError) as error:
        validate_email(email)
    assert error.value.code == "JA-203"
