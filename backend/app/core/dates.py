"""Local-day resolution.

"Today" in this app means the user's local calendar day, never UTC. That
distinction is the whole reason this module exists, and it is the source of a
whole class of bugs if left implicit.

Concretely: someone in Paris logging a late dinner at 00:30 on Tuesday is, in
UTC, at 23:30 on Monday. File it by UTC and it lands on the wrong day, their
Monday total silently gains 800 kcal, and Tuesday looks like they skipped dinner.

The rule this codebase follows: the **server** decides the date, from the
timezone stored on the user's profile. The client may say which date it wants to
read, but never which date something was logged on — a client's clock is
untrusted input like anything else it sends.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC_ZONE = ZoneInfo("UTC")


def resolve_zone(timezone_name: str) -> ZoneInfo:
    """Look up an IANA zone, falling back to UTC.

    Falls back rather than raising because an unknown zone must not make the app
    unusable — a stale profile or a device reporting an alias we do not have
    should cost a few hours of accuracy, not the ability to log food.

    Note for deployment: on Windows there is no system timezone database, so the
    `tzdata` package is a real runtime dependency rather than an optional extra.
    Without it every lookup here would fall back to UTC and the bug above would
    reappear on exactly the platform used for development.
    """
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC_ZONE


def local_today(timezone_name: str) -> date:
    """The current calendar date where the user is."""
    return datetime.now(resolve_zone(timezone_name)).date()


def local_now(timezone_name: str) -> datetime:
    return datetime.now(resolve_zone(timezone_name))
