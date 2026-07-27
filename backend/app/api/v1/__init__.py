"""Version 1 of the API.

Every v1 route is registered here and the whole router is mounted once, under
the `/api/v1` prefix, in `app.main`. Routers declare paths relative to that
prefix (`/health`, not `/api/v1/health`), so the version lives in exactly one
place instead of being repeated in every file.
"""

from fastapi import APIRouter

from app.api.v1 import auth, health, profile, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(profile.router)
