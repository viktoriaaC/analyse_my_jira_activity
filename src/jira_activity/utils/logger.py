"""The single logging setup for the project.

Only what is defined here may be logged: the HTTP method, the endpoint path
and the response status code. Tokens, auth headers, query parameters and
response bodies are never logged, and logs are never written to a file.
"""

import logging
import sys
from urllib.parse import urlsplit

LOGGER_NAME = "jira_activity"
_FORMAT = "%(levelname)s %(name)s: %(message)s"


def configure_logging(verbose: bool = False) -> None:
    """Send log records to stderr, at DEBUG if verbose, otherwise WARNING."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
    logger.propagate = False


def get_logger() -> logging.Logger:
    """Return the project logger."""
    return logging.getLogger(LOGGER_NAME)


def log_request(method: str, url: str, status_code: int) -> None:
    """Log an HTTP call as method, path and status code only."""
    path = urlsplit(url).path
    get_logger().debug("%s %s -> %d", method.upper(), path, status_code)
