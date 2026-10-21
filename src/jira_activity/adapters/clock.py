"""The system clock and timezone, kept in the I/O layer so the domain stays pure."""

from datetime import datetime, timezone, tzinfo


def now_utc() -> datetime:
    """The current time in UTC."""
    return datetime.now(timezone.utc)


def local_timezone() -> tzinfo:
    """The timezone of this computer, used to decide where days start and end."""
    return datetime.now().astimezone().tzinfo
