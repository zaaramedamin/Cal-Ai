"""User endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.db.models.food import Food, ReviewStatus
from app.db.session import get_session
from app.schemas.auth import UserRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class DeleteAccountRequest(BaseModel):
    """Confirmation for the one action that cannot be undone.

    The email rather than the password: a password field on a destructive
    action reads as "prove it is you", which the bearer token already did. This
    asks "are you sure", which is the actual question — and typing your own
    address out is a deliberate act in a way that tapping OK is not.
    """

    email: EmailStr


@router.get("/me", response_model=UserRead, summary="The signed-in user")
async def read_current_user(user: CurrentUser) -> UserRead:
    """Return the caller's own account.

    The proof that the protected-route dependency works, and the endpoint the
    mobile app calls on launch to decide whether a stored token is still good.

    There is no `/users/{id}` beside this, and there should not be. Every route
    in this app answers for *the caller*, so authorisation is a property of the
    route rather than a check someone has to remember to write. Adding an
    id parameter is what creates the classic bug where a user changes the number
    in the URL and reads someone else's data.
    """
    return UserRead.model_validate(user)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your account and everything in it",
)
async def delete_current_user(
    payload: DeleteAccountRequest,
    user: CurrentUser,
    session: SessionDep,
) -> Response:
    """Erase the account, its diary, its weights and its custom foods.

    **Confirmed by typing the email address**, not by a checkbox. This is the
    one irreversible action in the app and there is no undo, no grace period and
    no export — so the confirmation has to be something you cannot do by
    accident with a fat thumb on a small screen.

    **What survives, and why it is not a loophole.**

    Foods this person contributed and had *approved* stay in the shared
    database, and their `owner_id` becomes null. That is deliberate: an approved
    food is in other people's diaries, and cascading it away would silently
    rewrite what those people ate. The same reasoning already governs
    `food_reports.reporter_id` — the evidence outlives the account. Nothing
    identifying remains attached; what stays is a nutrition row a reviewer
    approved, which was never personal data.

    Everything actually personal — diary entries, weights, the profile, saved
    meals, recipes, sessions, private foods — is removed by the foreign keys,
    which is why this handler is three lines rather than a deletion script that
    someone has to remember to extend.
    """
    if payload.email.strip().lower() != user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That is not the email address on this account.",
        )

    # Detach approved contributions before the cascade reaches them. `foods`
    # cascades on `owner_id`, which would take shared, approved rows with it.
    await session.execute(
        update(Food)
        .where(Food.owner_id == user.id, Food.review_status == ReviewStatus.APPROVED)
        .values(owner_id=None)
    )

    await session.delete(user)
    await session.commit()

    logger.info("Account %s deleted at the owner's request", user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
