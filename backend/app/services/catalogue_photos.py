"""Catalogue photos, stored in Postgres.

**Why the database and not a folder on disk.** A folder means the API server has
state that has to be backed up separately, survive a redeploy, and be shared
between instances. Thirty-five thumbnails at ~20 KB is under a megabyte in total
— small enough that putting them where the rest of the catalogue already lives
removes a whole category of deployment problem for no meaningful cost.

A `bytea` column rather than an object store, for the same reason. Supabase
Storage and S3 exist for files that outgrow a row; these do not come close, and
using one would add a second system to configure, secure and back up in exchange
for nothing.

**Every image is decoded and re-encoded on the way in.** That does three jobs at
once: it caps the size, it normalises everything to one format so the serving
endpoint has one content type to think about, and it means the bytes we hand back
are bytes we generated rather than a file someone handed us.
"""

import hashlib
import io
import logging

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import Food, FoodPhoto

logger = logging.getLogger(__name__)

#: Longest edge after resizing. A tile renders about 110pt wide, so 512px covers
#: a 3x screen and the larger sheet header with room to spare. Going higher
#: multiplies the bytes for pixels no phone will ever show.
MAX_EDGE = 512

#: JPEG quality. 82 is the usual knee of the curve — visually indistinguishable
#: from 95 on photographs, at roughly half the size.
JPEG_QUALITY = 82

#: Refuse anything implausible as a food photo before decoding it. Pillow will
#: happily start decompressing a 200 MP image and exhaust memory doing it.
MAX_SOURCE_BYTES = 12 * 1024 * 1024
MAX_SOURCE_PIXELS = 80_000_000


class UnusablePhoto(ValueError):
    """The file is not an image we can use. Carries a reason worth showing."""


def process(raw: bytes, slug: str) -> tuple[str, bytes, int, int]:
    """Decode, square-crop, resize and re-encode.

    Returns `(name, jpeg_bytes, width, height)`.

    The name embeds a hash of the output, which is what makes the serving URL
    immutable: a changed photo produces a different name, so the client can cache
    the old one forever and still see the new one immediately. Cache invalidation
    by renaming rather than by header.
    """
    if len(raw) > MAX_SOURCE_BYTES:
        raise UnusablePhoto(f"{len(raw) // 1024 // 1024} MB is too large (limit 12 MB)")

    try:
        source = Image.open(io.BytesIO(raw))
        source.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise UnusablePhoto(f"not a readable image ({exc})") from exc

    if source.width * source.height > MAX_SOURCE_PIXELS:
        raise UnusablePhoto("image has implausibly many pixels")

    # Honour the camera's rotation tag before cropping. Skipping this is why
    # phone photos so often appear sideways in an app but upright in the gallery.
    source = _apply_exif_rotation(source)

    # Square-crop from the centre. The grid tiles are square, and letting the
    # component crop instead would mean each platform's `resizeMode` deciding
    # what gets cut off — usually the food.
    edge = min(source.width, source.height)
    left = (source.width - edge) // 2
    top = (source.height - edge) // 2
    square = source.crop((left, top, left + edge, top + edge))

    if edge > MAX_EDGE:
        square = square.resize((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

    # Flatten to RGB. A PNG with alpha would otherwise fail to save as JPEG, and
    # a white background is right for food shots on white cards.
    if square.mode in ("RGBA", "LA", "P"):
        square = square.convert("RGBA")
        flattened = Image.new("RGB", square.size, (255, 255, 255))
        flattened.paste(square, mask=square.split()[-1])
        square = flattened
    elif square.mode != "RGB":
        square = square.convert("RGB")

    buffer = io.BytesIO()
    square.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    data = buffer.getvalue()

    digest = hashlib.sha256(data).hexdigest()[:8]
    return f"{slug}-{digest}.jpg", data, square.width, square.height


def _apply_exif_rotation(image: Image.Image) -> Image.Image:
    """Rotate per the EXIF orientation tag, if there is one."""
    try:
        from PIL import ImageOps

        return ImageOps.exif_transpose(image) or image
    except Exception:  # noqa: BLE001 - a missing or corrupt tag must not fail an import
        return image


async def store_photo(
    session: AsyncSession,
    slug: str,
    raw: bytes,
    *,
    source_url: str | None = None,
    license: str | None = None,  # noqa: A002 - the column is named for the concept
    attribution: str | None = None,
) -> str:
    """Process an image, save it, and point the food at it.

    Returns the stored name. Older photos for the same food are deleted, so
    re-importing does not accumulate orphans nobody can reach.

    The credit arguments default to `None` because a photograph taken for this
    project owes credit to nobody. They are stored on the row rather than logged,
    because a CC BY-SA licence requires the credit to appear wherever the image
    does — which means the app has to be able to read it back.
    """
    food = (
        await session.execute(select(Food).where(Food.slug == slug))
    ).scalar_one_or_none()
    if food is None:
        raise UnusablePhoto(f"no catalogue food called {slug!r}")

    name, data, width, height = process(raw, slug)

    # Delete the food's other photos first, then insert. The reverse order would
    # delete the row we just wrote, because the new photo belongs to the same
    # food as the old ones.
    await session.execute(
        FoodPhoto.__table__.delete().where(
            FoodPhoto.food_id == food.id, FoodPhoto.name != name
        )
    )

    existing = await session.get(FoodPhoto, name)
    if existing is None:
        session.add(
            FoodPhoto(
                name=name,
                food_id=food.id,
                data=data,
                content_type="image/jpeg",
                width=width,
                height=height,
                bytes=len(data),
                source_url=source_url,
                license=license,
                attribution=attribution,
            )
        )
    else:
        # Same bytes, re-imported. The credit may still have changed — a licence
        # corrected on Commons, say — so it is refreshed rather than left stale.
        existing.source_url = source_url
        existing.license = license
        existing.attribution = attribution

    await session.execute(update(Food).where(Food.id == food.id).values(photo=name))
    await session.commit()

    logger.info("Stored photo %s (%d×%d, %d KB)", name, width, height, len(data) // 1024)
    return name


async def get_photo(session: AsyncSession, name: str) -> FoodPhoto | None:
    return await session.get(FoodPhoto, name)


async def list_credits(session: AsyncSession) -> list[tuple[str, str, str, str, str | None]]:
    """Every photo that owes somebody credit, alphabetically by food.

    Rows with no attribution are excluded rather than rendered as "Unknown": a
    photograph taken for this project owes nobody, and listing it under a credits
    heading would imply otherwise.
    """
    rows = await session.execute(
        select(
            Food.slug,
            Food.name,
            FoodPhoto.attribution,
            FoodPhoto.license,
            FoodPhoto.source_url,
        )
        .join(FoodPhoto, FoodPhoto.name == Food.photo)
        .where(FoodPhoto.attribution.is_not(None))
        .order_by(Food.name)
    )
    return [tuple(row) for row in rows.all()]  # type: ignore[misc]
