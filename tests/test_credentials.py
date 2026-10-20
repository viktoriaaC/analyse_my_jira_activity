import keyring
import pytest
from keyring.errors import KeyringError, PasswordSetError

from jira_activity.adapters.credentials import (
    Credentials,
    KeyringStore,
    configure,
    resolve_credentials,
    token_key,
)

SITE = "https://acme.atlassian.net"
EMAIL = "me@acme.se"


class FakeStore:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.reads = []

    def get(self, name):
        self.reads.append(name)
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value


class FakePrompter:
    def __init__(self, answers=(), confirm=False, interactive=True):
        self.answers = list(answers)
        self.asked = []
        self.confirm_answer = confirm
        self.confirm_asked = []
        self.interactive = interactive

    def ask(self, label, secret=False):
        self.asked.append((label, secret))
        return self.answers.pop(0)

    def confirm(self, question):
        self.confirm_asked.append(question)
        return self.confirm_answer


def stored_all():
    return FakeStore({"site": SITE, "email": EMAIL, token_key(EMAIL): "stored-token"})


# --- resolve order ---

def test_cli_options_win_over_everything():
    env = {"JIRA_SITE": "https://env.atlassian.net", "JIRA_EMAIL": "env@x.se", "JIRA_API_TOKEN": "env-token"}
    store = stored_all()
    result = resolve_credentials(SITE, EMAIL, "cli-token", env=env, store=store, prompter=FakePrompter())
    assert result == Credentials(SITE, EMAIL, "cli-token")
    assert store.reads == []


def test_env_vars_win_over_keychain():
    env = {"JIRA_SITE": SITE, "JIRA_EMAIL": EMAIL, "JIRA_API_TOKEN": "env-token"}
    store = stored_all()
    result = resolve_credentials(None, None, None, env=env, store=store, prompter=FakePrompter())
    assert result.token == "env-token"
    assert store.reads == []


def test_keychain_is_used_when_no_option_or_env():
    result = resolve_credentials(None, None, None, env={}, store=stored_all(), prompter=FakePrompter())
    assert result == Credentials(SITE, EMAIL, "stored-token")


def test_token_is_looked_up_for_the_resolved_email():
    store = FakeStore({token_key("other@acme.se"): "other-token"})
    result = resolve_credentials(SITE, "other@acme.se", None, env={}, store=store, prompter=FakePrompter())
    assert result.token == "other-token"


def test_prompt_is_last_and_token_is_hidden():
    prompter = FakePrompter(answers=[SITE, EMAIL, "typed-token"])
    result = resolve_credentials(None, None, None, env={}, store=FakeStore(), prompter=prompter)
    assert result == Credentials(SITE, EMAIL, "typed-token")
    assert prompter.asked == [("Jira site URL", False), ("Jira email", False), ("Jira API token", True)]


def test_empty_values_count_as_missing():
    env = {"JIRA_SITE": "", "JIRA_EMAIL": "", "JIRA_API_TOKEN": ""}
    result = resolve_credentials("", None, None, env=env, store=stored_all(), prompter=FakePrompter())
    assert result == Credentials(SITE, EMAIL, "stored-token")


def test_missing_value_without_terminal_raises():
    with pytest.raises(Exception) as error:
        resolve_credentials(SITE, EMAIL, None, env={}, store=FakeStore(), prompter=FakePrompter(interactive=False))
    assert error.value.code == "JA-302"


def test_empty_prompt_answer_raises():
    with pytest.raises(Exception) as error:
        resolve_credentials(SITE, EMAIL, None, env={}, store=FakeStore(), prompter=FakePrompter(answers=[""]))
    assert error.value.code == "JA-302"


def test_resolving_never_saves_anything():
    store = FakeStore()
    resolve_credentials(None, None, None, env={}, store=store, prompter=FakePrompter(answers=[SITE, EMAIL, "t"]))
    assert store.values == {}


def test_token_is_hidden_in_repr():
    assert "secret" not in repr(Credentials(SITE, EMAIL, "secret"))


# --- configure ---

def test_configure_saves_only_after_yes():
    store = FakeStore()
    prompter = FakePrompter(answers=["new-token"], confirm=True)
    assert configure(SITE + "/", EMAIL, store=store, prompter=prompter) is True
    assert store.values == {"site": SITE, "email": EMAIL, token_key(EMAIL): "new-token"}
    assert prompter.asked == [("Jira API token", True)]
    assert prompter.confirm_asked == ["Save site, email and token in the OS keychain?"]


def test_configure_saves_nothing_after_no():
    store = FakeStore()
    assert configure(SITE, EMAIL, store=store, prompter=FakePrompter(answers=["t"], confirm=False)) is False
    assert store.values == {}


def test_configure_rejects_bad_site_before_asking_for_token():
    prompter = FakePrompter(answers=["t"], confirm=True)
    with pytest.raises(Exception) as error:
        configure("http://acme.atlassian.net", EMAIL, store=FakeStore(), prompter=prompter)
    assert error.value.code == "JA-202"
    assert prompter.asked == []


def test_configure_without_terminal_raises():
    with pytest.raises(Exception) as error:
        configure(SITE, EMAIL, store=FakeStore(), prompter=FakePrompter(interactive=False))
    assert error.value.code == "JA-302"


# --- keychain adapter (real keyring module, patched so the real keychain is never touched) ---

def test_keyring_store_reads_and_writes_under_service(monkeypatch):
    saved = {}
    monkeypatch.setattr(keyring, "set_password", lambda service, name, value: saved.update({(service, name): value}))
    monkeypatch.setattr(keyring, "get_password", lambda service, name: saved.get((service, name)))
    store = KeyringStore()
    store.set("email", EMAIL)
    assert store.get("email") == EMAIL
    assert saved == {("jira-activity", "email"): EMAIL}


@pytest.mark.parametrize("exception", [KeyringError("boom"), RuntimeError("backend crashed")])
def test_keyring_read_failure_raises_store_error(monkeypatch, exception):
    def fail(service, name):
        raise exception
    monkeypatch.setattr(keyring, "get_password", fail)
    with pytest.raises(Exception) as error:
        KeyringStore().get("site")
    assert error.value.code == "JA-301"


def test_keyring_write_failure_raises_store_error(monkeypatch):
    def fail(service, name, value):
        raise PasswordSetError("locked")
    monkeypatch.setattr(keyring, "set_password", fail)
    with pytest.raises(Exception) as error:
        KeyringStore().set("site", SITE)
    assert error.value.code == "JA-301"


def test_keyring_error_never_contains_token(monkeypatch):
    def fail(service, name, value):
        raise PasswordSetError(f"could not store {value}")
    monkeypatch.setattr(keyring, "set_password", fail)
    with pytest.raises(Exception) as error:
        KeyringStore().set(token_key(EMAIL), "secret-token")
    assert "secret-token" not in str(error.value)


def test_default_store_is_keyring(monkeypatch):
    monkeypatch.setattr(keyring, "get_password", lambda service, name: {"site": SITE, "email": EMAIL}.get(name))
    result = resolve_credentials(None, None, "t", env={}, prompter=FakePrompter())
    assert (result.site, result.email) == (SITE, EMAIL)
