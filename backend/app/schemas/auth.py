"""Request and response models for authentication."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# NIST SP 800-63B: require at least 8 characters, allow long passphrases, and do
# not impose composition rules (no "must contain a symbol"). Those rules push
# people towards `Password1!` — predictable to a cracker, annoying to a human.
# Length is what actually helps.
#
# The genuinely effective next step is checking against known-breached passwords
# via the Have I Been Pwned range API, which never sees the password itself. Not
# built now; noted as the highest-value auth improvement available later.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class LoginRequest(BaseModel):
    # Not EmailStr: a login attempt with a malformed address should fail as
    # "wrong credentials", not as a 422 validation error that tells an attacker
    # their guess was not even a valid email.
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    """A user, as the client is allowed to see them.

    Note what is absent: `password_hash`. Defining responses as explicit schemas
    rather than serialising the ORM object is what makes that omission
    structural. Return the model directly and every column ships to the client,
    including the ones added six months from now by someone who did not think
    about this endpoint.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the access token expires.")


class PasswordResetRequest(BaseModel):
    # Plain str, not EmailStr, for the same reason as LoginRequest: a malformed
    # address should get the same neutral answer as a valid one, not a 422 that
    # confirms the format was at least right.
    email: str


class PasswordResetRequested(BaseModel):
    """Always the same message, whether or not the account exists.

    Confirming "no account with that email" here would turn this endpoint into a
    free account-enumeration oracle — and unlike registration, there is no
    usability argument for leaking it, because the honest message reads perfectly
    well either way.
    """

    message: str = "If an account exists for that address, a reset link is on its way."

    #: Development only. Lets the flow be tested without a mail provider, and is
    #: never populated when ENVIRONMENT is anything but `development`.
    debug_reset_token: str | None = None


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class AuthResponse(TokenPair):
    """Returned by register and login.

    Includes the user so the app can populate its auth state without a second
    round trip — on a phone, on mobile data, saving a request is worth more than
    the purity of one-resource-per-response.
    """

    user: UserRead
