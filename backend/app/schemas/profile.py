"""Profile, targets and weight schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.nutrition.targets import (
    MAX_HEIGHT_CM,
    MAX_WEIGHT_KG,
    MIN_HEIGHT_CM,
    MIN_WEIGHT_KG,
    ActivityLevel,
    Goal,
    Sex,
)


class ProfileInput(BaseModel):
    """What onboarding collects.

    Bounds are imported from the targets module rather than retyped, so the API
    and the calculator can never disagree about what counts as valid. Duplicated
    literals here would drift the first time one side changed.
    """

    sex: Sex
    birth_date: date
    height_cm: float = Field(ge=MIN_HEIGHT_CM, le=MAX_HEIGHT_CM)
    weight_kg: float = Field(ge=MIN_WEIGHT_KG, le=MAX_WEIGHT_KG)
    activity_level: ActivityLevel
    goal: Goal
    target_weight_kg: float | None = Field(default=None, ge=MIN_WEIGHT_KG, le=MAX_WEIGHT_KG)
    #: IANA name. Sent once by the device, then used server-side to decide which
    #: local day a diary entry belongs to.
    timezone: str = Field(default="UTC", max_length=64)

    @field_validator("birth_date")
    @classmethod
    def _reject_future_and_absurd_dates(cls, value: date) -> date:
        """A birth date in the future produces a negative age and a nonsense BMR.

        The age *range* is enforced by the targets module; this catches the
        specific input that would otherwise reach it as a plausible-looking
        number.
        """
        if value > date.today():
            raise ValueError("Birth date cannot be in the future.")
        return value


class MacroTargetsRead(BaseModel):
    protein_g: int
    carbs_g: int
    fat_g: int


class DerivationStepRead(BaseModel):
    label: str
    value: str
    detail: str


class TargetsRead(BaseModel):
    """A daily target, plus everything needed to explain it.

    The derivation ships with the numbers rather than being reconstructed in the
    app. Users trust a number they can follow, and describing the maths again in
    the UI layer would let the explanation drift away from the calculation.
    """

    bmr: int
    tdee: int
    calories: int
    uncapped_calories: int
    macros: MacroTargetsRead
    was_clamped: bool
    warnings: list[str]
    derivation: list[DerivationStepRead]


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sex: Sex
    birth_date: date
    height_cm: float
    activity_level: ActivityLevel
    goal: Goal
    target_weight_kg: float | None
    timezone: str
    onboarding_completed_at: datetime | None


class ProfileWithTargets(BaseModel):
    profile: ProfileRead
    current_weight_kg: float
    targets: TargetsRead


class WeightEntryInput(BaseModel):
    weight_kg: float = Field(ge=MIN_WEIGHT_KG, le=MAX_WEIGHT_KG)
    #: Defaults to the user's local today, resolved server-side.
    recorded_on: date | None = None


class WeightEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    weight_kg: float
    recorded_on: date
