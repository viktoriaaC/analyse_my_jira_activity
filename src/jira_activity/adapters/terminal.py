"""Terminal I/O for the CLI: the report, messages, errors and the progress spinner.

Output that is redirected to a file or pipe is switched to UTF-8, so characters such as
the timeline bar (█) never fail on Windows, where redirected output defaults to cp1252.
"""

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TextIO

from rich.console import Console
from rich.text import Text

from jira_activity.adapters.renderer import render_report
from jira_activity.domain.report import Report
from jira_activity.errors import OutputWriteError

UTF8_NAMES = {"utf-8", "utf8"}


class SafeConsole(Console):
    """A rich Console that reports a closed pipe as an error.

    By default rich silently exits the program (SystemExit 1) when the pipe closes,
    which would skip the tool's own error handling and message.
    """

    def on_broken_pipe(self) -> None:
        raise BrokenPipeError()


def utf8_stream(stream: TextIO) -> TextIO:
    """Make a redirected stream write UTF-8. Terminals are left alone: Python writes Unicode to them."""
    if stream.isatty() or (stream.encoding or "").lower() in UTF8_NAMES:
        return stream
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        # Not a reconfigurable text stream. Writing may then fail, which print_report reports as JA-401.
        pass
    return stream


def output_console() -> Console:
    """Console for the report and messages (stdout)."""
    return SafeConsole(file=utf8_stream(sys.stdout))


def error_console() -> Console:
    """Console for errors and progress (stderr), so they never mix into the report."""
    return SafeConsole(file=utf8_stream(sys.stderr))


def print_report(report: Report) -> None:
    """Print the report to stdout."""
    _write_safely(lambda: render_report(output_console(), report))


def print_message(message: str) -> None:
    """Print a plain message to stdout."""
    _write_safely(lambda: output_console().print(Text(message)))


def print_error(message: str) -> None:
    """Print an error message in red on stderr."""
    try:
        error_console().print(Text(message, style="bold red"))
    except (OSError, UnicodeEncodeError):
        # stderr itself is gone, so there is nowhere left to report this. The exit code still signals failure.
        pass


@contextmanager
def progress(message: str) -> Iterator[Callable[[str], None]]:
    """Show a spinner with the message on stderr while the block runs. Yields a function that changes the text."""
    with error_console().status(message) as status:
        yield status.update


def _write_safely(write: Callable[[], None]) -> None:
    """Run a write to stdout and turn output failures (closed pipe, encoding) into a tool error."""
    try:
        write()
    except (OSError, UnicodeEncodeError) as error:
        raise OutputWriteError(type(error).__name__) from error
