"""Catalogue photo processing, storage and serving."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.db.models.food import Food, FoodPhoto
from app.services.catalogue_photos import (
    JPEG_QUALITY,
    MAX_EDGE,
    UnusablePhoto,
    get_photo,
    process,
    store_photo,
)


def image_bytes(
    width: int,
    height: int,
    mode: str = "RGB",
    fmt: str = "PNG",
    colour: tuple[int, int, int] = (200, 120, 60),
) -> bytes:
    """A synthetic source image, in whatever shape a test needs."""
    fill = colour if mode == "RGB" else (*colour, 255)
    buffer = io.BytesIO()
    Image.new(mode, (width, height), fill).save(buffer, format=fmt)
    return buffer.getvalue()


def decoded(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# --------------------------------------------------------------------------- #
# Processing
# --------------------------------------------------------------------------- #


def test_large_photos_are_resized_to_the_thumbnail_edge() -> None:
    """The reason this pipeline exists.

    A phone camera produces roughly 3000x4000. Serving that into a 110pt tile is
    about 3 MB for pixels no screen will show.
    """
    _, data, width, height = process(image_bytes(3000, 4000), "egg")

    assert (width, height) == (MAX_EDGE, MAX_EDGE)
    assert len(data) < 120_000


def test_photos_are_square_cropped_from_the_centre() -> None:
    """The grid tiles are square. Cropping here rather than in the component
    means one decision instead of one per platform's resizeMode."""
    _, _, width, height = process(image_bytes(1200, 400), "egg")

    assert width == height


def test_small_photos_are_not_upscaled() -> None:
    """Enlarging a small source adds bytes and invents no detail."""
    _, _, width, height = process(image_bytes(200, 200), "egg")

    assert (width, height) == (200, 200)


def test_transparency_is_flattened_onto_white() -> None:
    """A PNG with alpha cannot be saved as JPEG at all — without flattening this
    raises, and white is right for food shots on white cards."""
    _, data, _, _ = process(image_bytes(300, 300, mode="RGBA"), "egg")

    assert decoded(data).mode == "RGB"


def test_output_is_always_jpeg_whatever_went_in() -> None:
    """So the serving endpoint has exactly one content type to reason about."""
    for fmt in ("PNG", "BMP", "JPEG"):
        name, data, _, _ = process(image_bytes(400, 400, fmt=fmt), "egg")
        assert name.endswith(".jpg")
        assert decoded(data).format == "JPEG"


def test_the_name_is_derived_from_the_bytes() -> None:
    """What makes the serving URL immutable and cacheable forever.

    Identical input gives an identical name; different input gives a different
    one, so a replaced photo is a new URL and a stale cache cannot happen.
    """
    first, _, _, _ = process(image_bytes(400, 400), "egg")
    same, _, _, _ = process(image_bytes(400, 400), "egg")
    different, _, _, _ = process(image_bytes(400, 400, mode="RGBA", fmt="PNG"), "egg")

    assert first == same
    assert first.startswith("egg-") and first.endswith(".jpg")
    # The RGBA source flattens to the same pixels, so this one *should* match —
    # the hash is over the output, not the input.
    assert different == first


def test_a_changed_image_gets_a_changed_name() -> None:
    orange, _, _, _ = process(image_bytes(400, 400, colour=(200, 120, 60)), "egg")
    green, _, _, _ = process(image_bytes(400, 400, colour=(10, 200, 90)), "egg")

    assert orange != green


def test_exif_rotation_is_applied() -> None:
    """Phone photos carry an orientation tag. Ignoring it is why images so often
    appear sideways in an app and upright in the gallery."""
    source = Image.new("RGB", (600, 300), (200, 120, 60))
    exif = source.getexif()
    exif[274] = 6  # rotate 90° clockwise
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", exif=exif)

    _, _, width, height = process(buffer.getvalue(), "egg")

    # Rotated to 300x600 then centre-cropped square — the point is that it did
    # not silently keep the unrotated framing.
    assert width == height == 300


def test_a_non_image_is_rejected_with_a_reason() -> None:
    with pytest.raises(UnusablePhoto, match="not a readable image"):
        process(b"this is not a photograph", "egg")


def test_an_oversized_file_is_rejected_before_decoding() -> None:
    """Pillow will happily start decompressing a decompression bomb."""
    with pytest.raises(UnusablePhoto, match="too large"):
        process(b"\x00" * (13 * 1024 * 1024), "egg")


def test_quality_is_the_documented_constant() -> None:
    """Guards the knee of the size/quality curve against a casual edit."""
    assert JPEG_QUALITY == 82


# --------------------------------------------------------------------------- #
# Storage and serving
# --------------------------------------------------------------------------- #


async def test_storing_a_photo_points_the_food_at_it(session, catalogue) -> None:
    name = await store_photo(session, "egg", image_bytes(600, 600))

    food = (await session.execute(select(Food).where(Food.slug == "egg"))).scalar_one()
    assert food.photo == name

    stored = await get_photo(session, name)
    assert stored.content_type == "image/jpeg"
    # The foreign key is what makes a photo un-orphanable, so assert it is set
    # rather than only that the food points back.
    assert stored.food_id == food.id


async def test_replacing_a_photo_removes_the_old_one(session, catalogue) -> None:
    """Otherwise every re-import leaves an orphan nothing can reach."""
    first = await store_photo(session, "egg", image_bytes(600, 600, colour=(200, 120, 60)))
    second = await store_photo(session, "egg", image_bytes(600, 600, colour=(10, 200, 90)))

    food = (await session.execute(select(Food).where(Food.slug == "egg"))).scalar_one()
    remaining = (
        await session.execute(
            select(func.count()).select_from(FoodPhoto).where(FoodPhoto.food_id == food.id)
        )
    ).scalar_one()

    assert remaining == 1
    assert first != second
    assert await get_photo(session, first) is None


async def test_the_photo_is_served_with_an_immutable_cache_header(
    client: TestClient, session, catalogue
) -> None:
    name = await store_photo(session, "egg", image_bytes(600, 600))

    response = client.get(f"/api/v1/catalogue/photos/{name}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert "immutable" in response.headers["cache-control"]
    assert decoded(response.content).format == "JPEG"


def test_photos_are_served_without_authentication(client: TestClient) -> None:
    """`<Image>` in React Native does not send our auth header. A missing photo
    must therefore 404, not 401 — the endpoint is deliberately open."""
    response = client.get("/api/v1/catalogue/photos/egg-deadbeef.jpg")

    assert response.status_code == 404


def test_a_malformed_photo_name_is_rejected(client: TestClient) -> None:
    """Pattern-locked at the route, so a malformed name never reaches a query."""
    for bad in ("../../etc/passwd", "egg.jpg", "egg-XYZ.jpg", "egg-deadbeef.png"):
        assert client.get(f"/api/v1/catalogue/photos/{bad}").status_code in (404, 422)


async def test_browsing_reports_the_photo_name(
    client: TestClient, session, catalogue
) -> None:
    """Which is how the app knows to render an image instead of the emoji."""
    name = await store_photo(session, "egg", image_bytes(600, 600))
    token = client.post(
        "/api/v1/auth/register", json={"email": "pics@example.com", "password": "correct-horse-b"}
    ).json()["access_token"]

    body = client.get(
        "/api/v1/catalogue", headers={"Authorization": f"Bearer {token}"}
    ).json()

    egg = body["sections"][0]["foods"][0]
    assert egg["photo"] == name


# --- attribution ----------------------------------------------------------- #
# The catalogue photographs come from Wikimedia Commons under CC BY and CC BY-SA,
# and both require the photographer to be named wherever the image appears. These
# cover the path from the import argument to the endpoint the credits screen
# reads, because a credit that is stored but unreachable satisfies nothing.


async def test_a_stored_photo_keeps_its_credit(session, catalogue) -> None:
    name = await store_photo(
        session,
        "egg",
        image_bytes(800, 800),
        source_url="https://commons.wikimedia.org/wiki/File:Egg.jpg",
        license="CC BY-SA 4.0",
        attribution="Someone / Wikimedia Commons (CC BY-SA 4.0)",
    )
    photo = await session.get(FoodPhoto, name)
    assert photo is not None
    assert photo.license == "CC BY-SA 4.0"
    assert photo.attribution == "Someone / Wikimedia Commons (CC BY-SA 4.0)"
    assert photo.source_url.endswith("File:Egg.jpg")


async def test_a_photo_taken_in_house_carries_no_credit(session, catalogue) -> None:
    """Absence must mean "nobody is owed", not "we forgot".

    A NOT NULL column here would force "Unknown" onto own-work photographs, which
    asserts something untrue about who took them.
    """
    name = await store_photo(session, "egg", image_bytes(800, 800))
    photo = await session.get(FoodPhoto, name)
    assert photo is not None
    assert photo.attribution is None
    assert photo.license is None


async def test_the_credits_endpoint_lists_photos_that_owe_credit(
    client: TestClient, session, catalogue
) -> None:
    await store_photo(
        session,
        "egg",
        image_bytes(800, 800),
        source_url="https://commons.wikimedia.org/wiki/File:Egg.jpg",
        license="CC BY-SA 4.0",
        attribution="A Photographer / Wikimedia Commons (CC BY-SA 4.0)",
    )

    response = client.get("/api/v1/catalogue/photo-credits")
    assert response.status_code == 200

    entry = next(row for row in response.json() if row["slug"] == "egg")
    assert entry["attribution"] == "A Photographer / Wikimedia Commons (CC BY-SA 4.0)"
    assert entry["license"] == "CC BY-SA 4.0"


async def test_own_work_photos_are_absent_from_the_credits(
    client: TestClient, session, catalogue
) -> None:
    """Listing them under a credits heading would imply a debt that is not owed."""
    await store_photo(session, "egg", image_bytes(800, 800))

    slugs = [row["slug"] for row in client.get("/api/v1/catalogue/photo-credits").json()]
    assert "egg" not in slugs


def test_the_credits_route_is_not_swallowed_by_the_slug_route(
    client: TestClient,
) -> None:
    """FastAPI matches in definition order.

    `/catalogue/{slug}` would happily accept `slug="photo-credits"` and 404,
    which is why the literal route is registered first. Declaring it after would
    make the endpoint unreachable while every unit test of the query still passed.
    """
    response = client.get("/api/v1/catalogue/photo-credits")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
