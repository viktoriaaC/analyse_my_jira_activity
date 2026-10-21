"""Find the Jira site, email and API token, and save them only when the user agrees.

Each value is taken from the first source that has it:
CLI option -> environment variable -> OS keychain -> interactive prompt.
Everything that is saved goes to the OS keychain; nothing is written to a plain file.
"""

import getpass
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

import keyring
from keyring.errors import KeyringError

from jira_activity.adapters.jira_client import validate_site_url
from jira_activity.errors import (
    CredentialStoreBackendError,
    CredentialStoreError,
    EmptyCredentialError,
    MissingCredentialsError,
    PromptAbortedError,
)

T = TypeVar("T")

KEYRING_SERVICE = "jira-activity"
SITE_KEY = "site"
EMAIL_KEY = "email"
TOKEN_KEY_PREFIX = "api-token:"

ENV_SITE = "JIRA_SITE"
ENV_EMAIL = "JIRA_EMAIL"
ENV_TOKEN = "JIRA_API_TOKEN"

SAVE_QUESTION = "Save site, email and token in the OS keychain?"


@dataclass(frozen=True)
class Credentials:
    """What is needed to call Jira. The token is left out of repr so it never ends up in output."""

    site: str
    email: str
    token: str = field(repr=False)


class CredentialStore(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...


class Prompter(Protocol):
    interactive: bool

    def ask(self, label: str, secret: bool = False) -> str: ...
    def confirm(self, question: str) -> bool: ...


class KeyringStore:
    """Reads and writes values in the OS keychain."""

    def get(self, name: str) -> str | None:
        return _call_keyring(f"reading '{name}'", lambda: keyring.get_password(KEYRING_SERVICE, name))

    def set(self, name: str, value: str) -> None:
        _call_keyring(f"saving '{name}'", lambda: keyring.set_password(KEYRING_SERVICE, name, value))


def _call_keyring(action: str, call: Callable[[], T]) -> T:
    """Run one keyring call and turn its failures into tool errors. Values never appear in the error."""
    try:
        return call()
    except KeyringError as error:
        raise CredentialStoreError(f"{action}: {type(error).__name__}") from error
    except Exception as error:
        raise CredentialStoreBackendError(f"{action}: {type(error).__name__}") from error


class ConsolePrompter:
    """Asks the user in the terminal. Not interactive when stdin is not a terminal."""

    def __init__(self) -> None:
        self.interactive = sys.stdin.isatty()

    def ask(self, label: str, secret: bool = False) -> str:
        prompt = f"{label}: "
        return _read_input(lambda: getpass.getpass(prompt) if secret else input(prompt)).strip()

    def confirm(self, question: str) -> bool:
        return _read_input(lambda: input(f"{question} [y/N]: ")).strip().lower() in ("y", "yes")


def _read_input(read: Callable[[], str]) -> str:
    """Read one answer, raising a tool error if the input ends (Ctrl+Z / Ctrl+D)."""
    try:
        return read()
    except EOFError as error:
        raise PromptAbortedError() from error


def token_key(email: str) -> str:
    """Keychain entry name for the token, so each email has its own token."""
    return TOKEN_KEY_PREFIX + email


def resolve_credentials(
    site: str | None,
    email: str | None,
    token: str | None,
    env: Mapping[str, str] | None = None,
    store: CredentialStore | None = None,
    prompter: Prompter | None = None,
) -> Credentials:
    """Return complete credentials, taking each value from the first source that has it."""
    env = os.environ if env is None else env
    store = store or KeyringStore()
    prompter = prompter or ConsolePrompter()
    site = resolve_value("Jira site URL", site, env.get(ENV_SITE), lambda: store.get(SITE_KEY), prompter)
    email = resolve_value("Jira email", email, env.get(ENV_EMAIL), lambda: store.get(EMAIL_KEY), prompter)
    token = resolve_value(
        "Jira API token", token, env.get(ENV_TOKEN), lambda: store.get(token_key(email)), prompter, secret=True
    )
    return Credentials(site=site, email=email, token=token)


def resolve_value(
    label: str,
    given: str | None,
    from_env: str | None,
    read_stored: Callable[[], str | None],
    prompter: Prompter,
    secret: bool = False,
) -> str:
    """Return the first non-empty value of: given, env, keychain, prompt. The keychain is read only if needed."""
    for value in (given, from_env):
        if value:
            return value
    stored = read_stored()
    if stored:
        return stored
    return ask_required(label, prompter, secret)


def ask_required(label: str, prompter: Prompter, secret: bool = False) -> str:
    """Ask the user for a value, or raise if that is not possible or the answer is empty."""
    if not prompter.interactive:
        raise MissingCredentialsError(f"{label} not given and no terminal to ask in")
    answer = prompter.ask(label, secret=secret)
    if not answer:
        raise EmptyCredentialError(label)
    return answer


def configure(
    site: str,
    email: str,
    store: CredentialStore | None = None,
    prompter: Prompter | None = None,
) -> bool:
    """Ask for the token and save site, email and token if the user agrees. Returns True if saved."""
    store = store or KeyringStore()
    prompter = prompter or ConsolePrompter()
    site = validate_site_url(site)
    token = ask_required("Jira API token", prompter, secret=True)
    credentials = Credentials(site=site, email=email, token=token)
    if not prompter.confirm(SAVE_QUESTION):
        return False
    save_credentials(credentials, store)
    return True


def save_credentials(credentials: Credentials, store: CredentialStore) -> None:
    """Write site, email and token to the store."""
    store.set(SITE_KEY, credentials.site)
    store.set(EMAIL_KEY, credentials.email)
    store.set(token_key(credentials.email), credentials.token)
