import io
import subprocess
import sys

import pytest

from jira_activity.adapters import terminal
from jira_activity.adapters.terminal import print_error, print_message, print_report, utf8_stream

DEMO_SCRIPT = """
from datetime import datetime, timezone
from jira_activity.adapters.terminal import print_report
from jira_activity.domain.models import DateRange, Issue, StatusInterval
from jira_activity.domain.report import build_report

start, end = datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 3, tzinfo=timezone.utc)
issue = Issue("ABC-1", "A ticket", "To Do", start)
print_report(build_report([issue], {"ABC-1": [StatusInterval("To Do", start, end)]}, DateRange(start, end)))
"""


def cp1252_stream():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def test_redirected_cp1252_stream_is_switched_to_utf8():
    stream = utf8_stream(cp1252_stream())
    stream.write("█ – ·")
    stream.flush()
    assert stream.buffer.getvalue().decode("utf-8") == "█ – ·"


def test_utf8_stream_is_left_unchanged():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    assert utf8_stream(stream) is stream


def test_redirected_report_on_windows_default_encoding_does_not_crash():
    """The real case: stdout is a pipe and Python picks the platform's default encoding."""
    env = {key: value for key, value in __import__("os").environ.items() if key != "PYTHONIOENCODING"}
    env["PYTHONUTF8"] = "0"
    result = subprocess.run([sys.executable, "-c", DEMO_SCRIPT], capture_output=True, env=env)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "█".encode("utf-8") in result.stdout


@pytest.mark.parametrize("failure", [BrokenPipeError(), UnicodeEncodeError("cp1252", "█", 0, 1, "no")])
def test_output_failures_become_ja_401(monkeypatch, failure):
    def fail(console, report):
        raise failure
    monkeypatch.setattr(terminal, "render_report", fail)
    with pytest.raises(Exception) as error:
        print_report(report=None)
    assert error.value.code == "JA-401"


def test_closed_pipe_raises_instead_of_silently_exiting():
    class BrokenStream(io.StringIO):
        def write(self, text):
            raise BrokenPipeError()
    with pytest.raises(BrokenPipeError):
        terminal.SafeConsole(file=BrokenStream()).print("x")


class BrokenTerminal(io.StringIO):
    """A stderr that looks like a terminal (so rich draws a spinner) but whose pipe is closed."""

    def write(self, text):
        raise BrokenPipeError()

    def isatty(self):
        return True


def test_progress_with_broken_stderr_lets_the_work_continue(monkeypatch):
    monkeypatch.setattr(sys, "stderr", BrokenTerminal())
    done = []
    with terminal.progress("Searching...") as update:
        update("step 1")
        done.append("work")
    assert done == ["work"]


def test_progress_does_not_hide_errors_from_the_work(monkeypatch):
    monkeypatch.setattr(sys, "stderr", BrokenTerminal())
    with pytest.raises(ValueError, match="from the work"):
        with terminal.progress("Searching..."):
            raise ValueError("from the work")


def test_progress_updates_text_on_a_working_stderr(monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    with terminal.progress("Searching...") as update:
        update("Reading history of ABC-1 (1/1)...")


def test_print_message_failure_becomes_ja_401(monkeypatch):
    class BrokenStdout(io.StringIO):
        def write(self, text):
            raise BrokenPipeError()
    monkeypatch.setattr(sys, "stdout", BrokenStdout())
    with pytest.raises(Exception) as error:
        print_message("hello")
    assert error.value.code == "JA-401"


def test_print_error_survives_a_broken_stderr(monkeypatch):
    class BrokenStderr(io.StringIO):
        def write(self, text):
            raise BrokenPipeError()
    monkeypatch.setattr(sys, "stderr", BrokenStderr())
    print_error("[JA-101] something")  # must not raise
