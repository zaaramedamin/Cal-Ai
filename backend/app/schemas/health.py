"""Health check response model."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Reported by `GET /api/v1/health`.

    `Literal` rather than `str` is deliberate: it makes the allowed values part
    of the OpenAPI schema, so the TypeScript client we generate in Phase 3 gets a
    union type and the mobile app cannot compare against a status that will never
    be sent.
    """

    status: Literal["ok", "degraded"] = Field(
        description="`degraded` means the API is up but a dependency is not."
    )
    version: str = Field(description="Backend version, so the app can spot a stale deploy.")
    db: Literal["ok", "unreachable"] = Field(
        description="Result of a real `SELECT 1` against Postgres."
    )
