"""Catalogue photos, stored in MongoDB.

**Why the database and not a folder on disk.** A folder means the API server has
state that has to be backed up separately, survive a redeploy, and be shared
between instances. Thirty-five thumbnails at ~20 KB is under a megabyte in total
— small enough that putting them where the rest of the catalogue already lives
removes a whole category of deployment problem for no meaningful cost.

Not GridFS, for the same reason. GridFS exists to chunk files past the 16 MB
document limit; these are two orders of magnitude below it, and chunking would
add a second collection and a join to read one thumbnail.

**Every image is decoded and re-encoded on the way in.** That does three jobs at
once: it caps the size, it normalises everything to one format so the serving
endpoint has one content type to think about, and it means the bytes we hand back
are bytes we generated rather than a file someone handed us.
"""

import hashlib
import io
import logging
from datetime import UTC, datetime
from typing import Any

from PIL import Image, UnidentifiedImageError
from pymongo import ASCENDING, IndexModel

from app.db.mongo import food_items, get_db

logger = logging.getLogger(__name__)

PHOTOS = "catalogue_photos"

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


def photos(database: Any = None) -> Any:
    """The photo collection, optionally on a caller-supplied database handle.

    The parameter exists for tests. A motor client binds to the event loop that
    created it, and `TestClient` runs the app on its own — so a test that both
    drives the API and seeds a photo directly needs to seed through *its* client,
    not the app's. Defaulting to the app's handle keeps every production call
    site unchanged.
    """
    # `is not None`, not `or`. A motor Database raises NotImplementedError on
    # truth testing precisely to stop this idiom being written by accident.
    return (get_db() if database is None else database)[PHOTOS]


async def ensure_photo_indexes() -> None:
    await photos().create_indexes(
        [
            IndexModel([("name", ASCENDING)], unique=True, name="uq_photo_name"),
            IndexModel([("slug", ASCENDING)], name="ix_photo_slug"),
        ]
    )


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


async def store_photo(slug: str, raw: bytes, *, database: Any = None) -> str:
    """Process an image, save it, and point the food at it.

    Returns the stored name. Old photos for the same slug are deleted, so
    re-importing does not accumulate orphans nobody can reach.
    """
    name, data, width, height = process(raw, slug)
    collection = photos(database)
    foods = food_items() if database is None else database["food_items"]

    await collection.update_one(
        {"name": name},
        {
            "$set": {
                "name": name,
                "slug": slug,
                "data": data,
                "content_type": "image/jpeg",
                "width": width,
                "height": height,
                "bytes": len(data),
                "created_at": datetime.now(UTC),
            }
        },
        upsert=True,
    )
    await collection.delete_many({"slug": slug, "name": {"$ne": name}})
    await foods.update_one({"slug": slug}, {"$set": {"photo": name}})

    logger.info("Stored photo %s (%d×%d, %d KB)", name, width, height, len(data) // 1024)
    return name


async def get_photo(name: str, *, database: Any = None) -> dict[str, Any] | None:
    return await photos(database).find_one({"name": name})
