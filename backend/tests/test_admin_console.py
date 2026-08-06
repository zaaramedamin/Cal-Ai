"""The admin console page.

Small surface, and the tests are mostly about what it is *not*: it has no
privileged access, holds no data, and cannot do anything the API would refuse.

The page's own behaviour is JavaScript and untested — there is no browser in
this suite. What is tested is the contract it depends on: the route exists, the
switch turns it off, and the endpoints behind it stay gated on `is_admin`
whatever the page does.
"""

import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.admin.router import PAGE
from app.core.config import get_settings


def test_the_console_is_served(client: TestClient) -> None:
    response = client.get("/admin")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_the_page_file_exists_and_is_a_document() -> None:
    """Guards the packaging, not the content.

    `FileResponse` on a missing path is a 500 at request time rather than an
    error at import, so a file left out of the wheel would only surface when
    somebody opened the console.
    """
    assert PAGE.is_file()
    assert PAGE.read_text(encoding="utf-8").lstrip().startswith("<!doctype html>")


def test_the_console_is_not_cached(client: TestClient) -> None:
    """A cached page talking to a newer API is a confusing failure."""
    assert client.get("/admin").headers["cache-control"] == "no-store"


def test_the_console_can_be_switched_off(client: TestClient, monkeypatch) -> None:
    """404, matching how the admin API answers a non-admin.

    A 403 would confirm the console exists and is merely disabled.
    """
    monkeypatch.setenv("ADMIN_UI_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert client.get("/admin").status_code == 404
    finally:
        monkeypatch.delenv("ADMIN_UI_ENABLED", raising=False)
        get_settings.cache_clear()


def test_config_says_which_sign_in_to_use(client: TestClient) -> None:
    """The page cannot guess this, and guessing wrong means nobody can sign in.

    Regression test for exactly that: the console shipped calling
    `/api/v1/auth/login`, and every account in this project is a Supabase Auth
    account with a null `password_hash`, so the form could never have worked.
    """
    body = client.get("/admin/config").json()

    assert set(body) == {"supabase_url", "supabase_anon_key"}
    settings = get_settings()
    assert body["supabase_url"] == settings.supabase_url
    # Empty is the signal to fall back to the hand-built endpoint, so the two
    # must agree rather than the page inferring one from the other.
    assert bool(body["supabase_url"]) is settings.supabase_auth_enabled


def test_config_follows_the_console_switch(client: TestClient, monkeypatch) -> None:
    """Turning the console off must not leave an endpoint behind advertising it."""
    monkeypatch.setenv("ADMIN_UI_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert client.get("/admin/config").status_code == 404
    finally:
        monkeypatch.delenv("ADMIN_UI_ENABLED", raising=False)
        get_settings.cache_clear()


def test_config_never_carries_a_real_secret(client: TestClient) -> None:
    """The anon key is publishable; nothing else on Settings is.

    Asserted because this endpoint is unauthenticated, so a field added here
    later is a field the whole internet can read.
    """
    body = client.get("/admin/config").json()
    settings = get_settings()

    assert settings.secret_key not in str(body)
    assert settings.usda_api_key not in str(body) or settings.usda_api_key == "DEMO_KEY"
    if settings.gemini_api_key:
        assert settings.gemini_api_key not in str(body)


def test_the_console_is_absent_from_the_api_schema(client: TestClient) -> None:
    """It is a page, not part of the contract the mobile client is built from."""
    schema = client.get("/api/v1/openapi.json").json()

    assert "/admin" not in schema["paths"]
    assert "/admin/config" not in schema["paths"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/review/queue"),
        ("get", "/api/v1/review/queue/stats"),
        ("get", "/api/v1/review/reports"),
    ],
)
def test_serving_the_page_grants_nothing(client: TestClient, method: str, path: str) -> None:
    """The console has no access of its own.

    It signs in as an ordinary admin and calls the same endpoints the phone
    does, so an anonymous caller who has loaded the page is exactly as
    unauthorised as one who has not. This is the property that makes serving the
    page publicly acceptable.
    """
    client.get("/admin")

    assert getattr(client, method)(path).status_code == 401


def test_the_page_holds_no_secrets() -> None:
    """It is served to anyone, so it must contain nothing worth having.

    Checked as a string rather than trusted: a key pasted in during debugging is
    exactly the kind of thing that survives to a commit.
    """
    source = PAGE.read_text(encoding="utf-8")
    settings = get_settings()

    assert settings.secret_key not in source
    for secret in (settings.usda_api_key, settings.gemini_api_key, settings.supabase_anon_key):
        if secret and secret != "DEMO_KEY":
            assert secret not in source


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_console_javascript_parses(tmp_path) -> None:
    """A syntax check on the page's script, because nothing else looks at it.

    There is no browser in this suite, so 360-odd lines of JavaScript ship on
    nobody's authority. `node --check` is the cheapest thing that would catch a
    stray brace — it will not catch a logic error, but a page that fails to
    parse renders a blank screen with the error only in a console nobody has
    open, which is the worst way to find out.

    Skipped rather than required when node is absent: the backend must stay
    installable without a JavaScript toolchain.
    """
    source = PAGE.read_text(encoding="utf-8")
    script = re.search(r"<script>(.*?)</script>", source, re.S)
    assert script is not None, "the console has no inline script"

    extracted = tmp_path / "console.js"
    extracted.write_text(script.group(1), encoding="utf-8")

    result = subprocess.run(  # noqa: S603 - fixed argv, path from tmp_path
        ["node", "--check", str(extracted)],  # noqa: S607
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_the_page_escapes_user_typed_text() -> None:
    """Food names and report notes are user input rendered into `innerHTML`.

    A submission named `<img onerror=...>` would otherwise run script in the one
    session that can approve foods into everybody's search. Asserted on the
    source because there is no browser here to prove it the honest way — which
    is a weak test, and better than trusting the comment above it.
    """
    source = PAGE.read_text(encoding="utf-8")

    assert "function escapeHtml" in source
    # Every interpolation of a name or a note goes through it.
    assert "escapeHtml(food.name)" in source
    assert "escapeHtml(r.note)" in source
    assert "escapeHtml(item.llm_reason)" in source


# --------------------------------------------------------------------------- #
# The notes tab's data
# --------------------------------------------------------------------------- #


async def test_inventory_is_admin_only(client: TestClient) -> None:
    """404, matching every other admin route, so probing maps nothing."""
    from tests.test_reports import account

    headers = account(client, "ordinary@example.com")
    assert client.get("/api/v1/review/inventory", headers=headers).status_code == 404


async def test_inventory_counts_what_is_missing(client: TestClient, session) -> None:
    """The numbers that decide what to work on next.

    Previously only answerable by writing SQL, which meant in practice they were
    not answered at all.
    """
    from app.db.models.food import Food, FoodSource
    from tests.test_reports import admin_account

    session.add(
        Food(
            source=FoodSource.INNTA,
            source_id="innta-001",
            name="Pain, tabouna",
            name_fr="Pain, tabouna",
            kcal=244,
            protein_g=8,
            carbs_g=44,
            fat_g=3,
        )
    )
    await session.commit()

    admin = await admin_account(client, session, "admin@example.com")
    body = client.get("/api/v1/review/inventory", headers=admin).json()

    assert body["foods_total"] == 1
    assert body["by_source"] == {"innta": 1}
    assert body["missing_photo"] == 1
    assert body["missing_portions"] == 1
    assert body["foods"][0]["name_fr"] == "Pain, tabouna"


async def test_inventory_can_list_only_foods_needing_a_photo(
    client: TestClient, session
) -> None:
    """The working list for the next shoot."""
    from app.db.models.food import Food, FoodSource
    from tests.test_reports import admin_account

    session.add_all(
        [
            Food(
                source=FoodSource.INNTA,
                source_id=f"innta-{n}",
                name=f"Food {n}",
                kcal=100,
                protein_g=1,
                carbs_g=1,
                fat_g=1,
                photo="something.jpg" if n == 1 else None,
            )
            for n in (1, 2)
        ]
    )
    await session.commit()

    admin = await admin_account(client, session, "admin@example.com")
    body = client.get(
        "/api/v1/review/inventory", headers=admin, params={"missing_photo": "true"}
    ).json()

    assert [f["name"] for f in body["foods"]] == ["Food 2"]
    # The totals still describe everything, not the filtered view — otherwise
    # "1 of 1 need a photo" would be true and useless.
    assert body["foods_total"] == 2


async def test_inventory_publishes_the_portions_still_wanted(
    client: TestClient, session
) -> None:
    """So the deliberate gaps are visible in the console, not only in a
    docstring nobody opens."""
    from tests.test_reports import admin_account

    admin = await admin_account(client, session, "admin@example.com")
    body = client.get("/api/v1/review/inventory", headers=admin).json()

    assert any("TABOUNA" in item for item in body["portions_wanted"])
