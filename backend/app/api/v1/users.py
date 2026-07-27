"""User endpoints."""

from fastapi import APIRouter

from app.core.deps import CurrentUser
from app.schemas.auth import UserRead

router = APIRouter(prefix="/users", tags=["users"])


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
