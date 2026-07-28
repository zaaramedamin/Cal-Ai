"""Maintenance commands.

    python -m app.cli seed-catalogue [--force]
    python -m app.cli import-photos <directory>

Deliberately a plain argv switch rather than Typer or Click. There are two
commands; a CLI framework would be a dependency and an abstraction earning their
keep against a couple of `if`s.
"""

import asyncio
import logging
import sys
from pathlib import Path

from app.db.mongo import close_client, ensure_indexes, food_items
from app.services.catalogue_photos import UnusablePhoto, ensure_photo_indexes, store_photo
from app.services.catalogue_seed import SEEDS, seed_catalogue

#: Extensions the importer will look at. Everything is re-encoded to JPEG, so
#: this is about what Pillow can open, not what gets stored.
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp"})


async def _seed(force: bool) -> int:
    await ensure_indexes()
    tally = await seed_catalogue(force=force)
    total = await food_items().count_documents({})
    await close_client()

    print(
        f"seeded {tally['seeded']}, skipped {tally['skipped']}, "
        f"failed {tally['failed']} — catalogue holds {total} of {len(SEEDS)} foods"
    )

    if total < len(SEEDS):
        # Almost always the DEMO_KEY hourly cap. Say so plainly: a partial
        # catalogue with no explanation looks like the seeder is broken, and the
        # fix is a free key rather than a code change.
        print(
            "\nIncomplete. Nearly always the USDA rate limit — DEMO_KEY allows 30 requests\n"
            "an hour and this catalogue is longer than that. The seeder is resumable, so\n"
            "either run it again later or put a free key in USDA_API_KEY:\n"
            "  https://fdc.nal.usda.gov/api-key-signup.html"
        )
        return 1
    return 0


async def _import_photos(directory: Path) -> int:
    """Import every image in `directory`, matching filenames to catalogue slugs.

    The filename **is** the mapping: `chicken-breast.jpg` becomes the photo for
    the `chicken-breast` food. No manifest to keep in sync, and renaming a file
    is how you re-point a photo.
    """
    if not directory.is_dir():
        print(f"Not a directory: {directory}")
        return 2

    await ensure_photo_indexes()

    known = {seed.slug for seed in SEEDS}
    files = sorted(p for p in directory.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)

    if not files:
        print(f"No images in {directory}. Looked for: {', '.join(sorted(IMAGE_SUFFIXES))}")
        await close_client()
        return 1

    imported = skipped = failed = 0
    for path in files:
        slug = path.stem.lower()

        if slug not in known:
            # Named rather than silently ignored: a typo in a filename would
            # otherwise look exactly like a successful import of nothing.
            print(f"  skip  {path.name} — no catalogue food called {slug!r}")
            skipped += 1
            continue

        try:
            name = await store_photo(slug, path.read_bytes())
        except UnusablePhoto as exc:
            print(f"  fail  {path.name} — {exc}")
            failed += 1
            continue

        print(f"  ok    {path.name} -> {name}")
        imported += 1

    # Checked before closing the client, not after.
    seeded = await food_items().count_documents({}) > 0
    await close_client()

    print(f"\nimported {imported}, skipped {skipped}, failed {failed}")

    if imported and not seeded:
        print(
            "\nNote: the catalogue itself is still empty, so these photos are stored\n"
            "but nothing displays them yet. Run `seed-catalogue` once USDA_API_KEY is set."
        )
    return 0 if imported else 1


def main() -> int:
    # Windows consoles default to cp1252, which cannot encode plenty of what this
    # app legitimately prints — the accented French food names, the em dash in
    # the summary line. Without this, a print() *crashes the command* partway
    # through, which on an importer means an unclear half-finished run. Belt and
    # braces: `errors="replace"` guarantees no character can ever raise.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    args = sys.argv[1:]

    if not args or args[0] in {"-h", "--help"}:
        print(__doc__)
        return 0

    if args[0] == "seed-catalogue":
        return asyncio.run(_seed(force="--force" in args))

    if args[0] == "import-photos":
        if len(args) < 2:
            print("Usage: python -m app.cli import-photos <directory>")
            return 2
        return asyncio.run(_import_photos(Path(args[1])))

    print(f"Unknown command: {args[0]}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
