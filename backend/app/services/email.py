"""Email delivery.

There is no email provider wired up yet, and pretending otherwise would be worse
than admitting it. This module exists so that the *seam* is real: the reset
endpoint calls `send_password_reset`, and swapping the log for Resend, Postmark
or SES in Phase 7 changes this file and nothing else.

Building it as a no-op logger rather than skipping it entirely matters, because
the alternative is putting `logger.info(token)` inline in the endpoint — and
inline debug logging is exactly the kind of thing that survives into production
and leaks reset tokens into a log aggregator.
"""

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def build_reset_link(token: str) -> str:
    """The deep link that opens the reset screen in the app.

    `calai://` is the scheme declared in the mobile app.config.ts. In production
    this should be an https link to a web page that redirects into the app, so
    that the email is still useful when opened on a machine without the app
    installed — noted for Phase 7.
    """
    return f"calai://reset-password?token={token}"


def send_password_reset(email: str, token: str) -> None:
    """Deliver a password reset link.

    Until a provider exists, the link goes to the application log so the flow is
    testable end to end in development.

    The token is logged at WARNING with an explicit marker, deliberately loud:
    a silent INFO line is easy to leave in place after adding a real provider,
    whereas this one is meant to be impossible to miss in a production log.
    """
    link = build_reset_link(token)
    settings = get_settings()

    if settings.is_development:
        logger.warning("PASSWORD RESET (dev only, no mailer configured) %s -> %s", email, link)
    else:
        # Never log the token outside development — production logs are widely
        # readable and frequently shipped to third-party services.
        logger.error(
            "Password reset requested for %s but no email provider is configured. "
            "The user cannot receive their link.",
            email,
        )
