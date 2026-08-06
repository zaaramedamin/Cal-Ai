"""Version 1 of the API.

Every v1 route is registered here and the whole router is mounted once, under
the `/api/v1` prefix, in `app.main`. Routers declare paths relative to that
prefix (`/health`, not `/api/v1/health`), so the version lives in exactly one
place instead of being repeated in every file.
"""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    catalogue,
    diary,
    foods,
    health,
    meals,
    profile,
    progress,
    recipes,
    review,
    scan,
    suggestions,
    users,
    water,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(profile.router)
api_router.include_router(foods.router)
api_router.include_router(catalogue.router)
api_router.include_router(meals.router)
api_router.include_router(diary.router)
api_router.include_router(recipes.router)
api_router.include_router(review.router)
api_router.include_router(progress.router)
api_router.include_router(scan.router)
api_router.include_router(suggestions.router)
api_router.include_router(water.router)
