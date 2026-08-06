"""Serving the console. One route, one file.

`FileResponse` rather than reading the HTML into a string at import: editing the
page and refreshing the browser is the whole development loop for something like
this, and a cached string would need a server restart per change.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["admin"])

PAGE = Path(__file__).parent / "console.html"


def _require_enabled() -> None:
    """404 when the console is switched off.

    Matching how the admin API answers a non-admin: a 403 would confirm the
    console exists and is merely disabled.
    """
    if not get_settings().admin_ui_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")


class ConsoleConfig(BaseModel):
    """What the page needs to know before anybody can sign in.

    **Why this endpoint exists at all.** Every account in this project is a
    Supabase Auth account — `password_hash` is null on all of them — so the
    console has to get its token from Supabase, exactly as the mobile app does,
    and it cannot do that without the project URL and the publishable key.

    **Neither value is a secret.** The anon key is compiled into the mobile app
    and Supabase's model assumes an attacker holds it; access is controlled by
    token verification and row-level security, never by hiding it. Serving it
    here gives away nothing that shipping the app has not already given away.
    """

    #: Empty when Supabase Auth is switched off, which is the signal to the page
    #: to fall back to the hand-built `/api/v1/auth/login`. The two coexist by
    #: design, so the console has to work either way.
    supabase_url: str
    supabase_anon_key: str


@router.get("/admin/config", response_model=ConsoleConfig, include_in_schema=False)
async def console_config() -> ConsoleConfig:
    """Which sign-in the console should use."""
    _require_enabled()

    settings = get_settings()
    return ConsoleConfig(
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
    )


@router.get("/admin", include_in_schema=False)
async def console() -> FileResponse:
    """The admin console.

    Excluded from the OpenAPI schema — it is a page, not part of the contract
    the mobile client is generated from.
    """
    _require_enabled()

    return FileResponse(
        PAGE,
        media_type="text/html",
        # The page is one file that changes when the backend is redeployed, and
        # a stale cached copy talking to a newer API is a confusing failure.
        headers={"Cache-Control": "no-store"},
    )
