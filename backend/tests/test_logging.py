"""That the application can log at all.

A one-test file, guarding a failure that reports nothing about itself.

`logging.config.fileConfig` defaults to `disable_existing_loggers=True`, and
alembic's generated `env.py` calls it. Every logger that already exists and is
not named in `alembic.ini` — which is all of ours — gets `disabled = True`,
permanently, in that process. Nothing raises. Log lines simply stop existing.

The suite runs migrations at session start, so this had silenced every
application log line in every test since alembic was introduced. It surfaced
only because a test asserted on a specific message and found none.

If this test fails, look at `disable_existing_loggers` in `alembic/env.py`
before looking anywhere else.
"""

import logging

import pytest

APP_LOGGERS = [
    "app.main",
    "app.api.v1.auth",
    "app.core.rate_limit_store",
    "app.services.usda",
]


@pytest.mark.parametrize("name", APP_LOGGERS)
def test_application_loggers_are_not_disabled(name: str) -> None:
    assert not logging.getLogger(name).disabled, (
        f"{name} is disabled — something has called fileConfig or dictConfig "
        "with disable_existing_loggers left at its default of True"
    )


def test_a_log_record_reaches_a_handler(caplog) -> None:
    """The end-to-end version: emitting actually produces a record.

    Checking the `disabled` flag alone would miss a filter or a broken
    propagate chain doing the same damage by another route.
    """
    with caplog.at_level(logging.WARNING, logger="app.core.rate_limit_store"):
        logging.getLogger("app.core.rate_limit_store").warning("audible")

    assert [r.message for r in caplog.records] == ["audible"]
