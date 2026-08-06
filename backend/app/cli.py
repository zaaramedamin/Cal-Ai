"""Maintenance commands.

    python -m app.cli seed-catalogue [--force]
    python -m app.cli import-photos <directory>
    python -m app.cli find-photos <directory>
    python -m app.cli import-picks <picks.json>
    python -m app.cli import-foods <dataset.json> [--only INNTA|Ciqual|FoodDataCentral]
    python -m app.cli apply-portions [--replace]

Deliberately a plain argv switch rather than Typer or Click. A CLI framework
would be a dependency and an abstraction earning their keep against a handful of
`if`s.

**`import-foods` writes to whatever `DATABASE_URL` points at**, which on this
project is a hosted Supabase instance with real users on it. Check before
running it, and prefer `--only INNTA` for a first pass: 228 rows are reviewable,
4,021 are not.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.core.tls import use_system_trust_store
from app.db.models.food import Food, FoodKind
from app.db.session import SessionFactory, engine
from app.services.catalogue_photo_picks import (
    QUERIES,
    fetch_picked,
    gather,
    write_contact_sheet,
)
from app.services.catalogue_photos import UnusablePhoto, store_photo
from app.services.catalogue_seed import SEEDS, seed_catalogue

#: Extensions the importer will look at. Everything is re-encoded to JPEG, so
#: this is about what Pillow can open, not what gets stored.
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp"})


async def _catalogue_count(session) -> int:
    query = select(func.count()).select_from(Food).where(Food.kind == FoodKind.CATALOGUE)
    return (await session.execute(query)).scalar_one()


async def _seed(force: bool) -> int:
    async with SessionFactory() as session:
        tally = await seed_catalogue(session, force=force)
        total = await _catalogue_count(session)
    await engine.dispose()

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

    known = {seed.slug for seed in SEEDS}
    files = sorted(p for p in directory.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)

    if not files:
        print(f"No images in {directory}. Looked for: {', '.join(sorted(IMAGE_SUFFIXES))}")
        return 1

    imported = skipped = failed = 0
    async with SessionFactory() as session:
        for path in files:
            slug = path.stem.lower()

            if slug not in known:
                # Named rather than silently ignored: a typo in a filename would
                # otherwise look exactly like a successful import of nothing.
                print(f"  skip  {path.name} — no catalogue food called {slug!r}")
                skipped += 1
                continue

            try:
                name = await store_photo(session, slug, path.read_bytes())
            except UnusablePhoto as exc:
                print(f"  fail  {path.name} — {exc}")
                failed += 1
                continue

            print(f"  ok    {path.name} -> {name}")
            imported += 1

        seeded = await _catalogue_count(session) > 0

    await engine.dispose()

    print(f"\nimported {imported}, skipped {skipped}, failed {failed}")

    if imported and not seeded:
        print(
            "\nNote: the catalogue itself is still empty, so these photos are stored\n"
            "but nothing displays them yet. Run `seed-catalogue` once USDA_API_KEY is set."
        )
    return 0 if imported else 1


def _find_photos(directory: Path) -> int:
    """Search Wikimedia Commons and write a contact sheet to choose from.

    Nothing is imported here and nothing is decided here. The command gathers
    freely-licensed candidates and hands the choosing to a person, because an
    automatic pick for "chicken breast" is a photograph of live chickens.
    """
    directory.mkdir(parents=True, exist_ok=True)

    slugs = [seed.slug for seed in SEEDS]
    missing = [slug for slug in slugs if slug not in QUERIES]
    if missing:
        print(f"No search term for: {', '.join(missing)}")
        print("Add one to catalogue_photo_picks.QUERIES, or photograph these yourself.\n")

    print(f"Searching Commons for {len(slugs) - len(missing)} foods...\n")
    results = gather(slugs)

    names = {seed.slug: seed.name_en for seed in SEEDS}
    sheet = write_contact_sheet(results, directory / "contact-sheet.html", names)

    empty = [slug for slug, found in results.items() if not found]
    total = sum(len(found) for found in results.values())

    print(f"\n{total} candidates for {len(results) - len(empty)} foods.")
    if empty:
        print(f"Nothing usable for: {', '.join(empty)}")
        print("Those need a photograph taking, or a better search term.")

    print(f"\nOpen this, click one image per food, press Copy:\n  {sheet}")
    print(
        f"\nThen save what you copied and run:"
        f"\n  python -m app.cli import-picks {directory / 'picks.json'}"
    )
    return 0


async def _import_picks(path: Path) -> int:
    """Download and store the photographs chosen in the contact sheet."""
    if not path.is_file():
        print(f"No such file: {path}")
        print("Save the JSON you copied from the contact sheet to this path first.")
        return 2

    try:
        picks = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"{path.name} is not valid JSON: {exc}")
        return 2

    if not isinstance(picks, dict) or not picks:
        print("Expected a JSON object of {slug: candidate}. Nothing to import.")
        return 2

    known = {seed.slug for seed in SEEDS}
    unknown = [slug for slug in picks if slug not in known]
    if unknown:
        print(f"Not catalogue foods, ignoring: {', '.join(unknown)}")
        picks = {slug: pick for slug, pick in picks.items() if slug in known}

    print(f"Downloading {len(picks)} photographs...\n")
    fetched = fetch_picked(picks)

    imported = failed = 0
    async with SessionFactory() as session:
        for slug, (data, credit) in fetched.items():
            try:
                name = await store_photo(session, slug, data, **credit)
            except UnusablePhoto as exc:
                print(f"  fail  {slug} — {exc}")
                failed += 1
                continue
            print(f"  ok    {slug} -> {name}  ({credit['license']})")
            imported += 1

    await engine.dispose()

    failed += len(picks) - len(fetched)
    print(f"\nimported {imported}, failed {failed}")
    return 0 if imported else 1


async def _import_foods(path: Path, only: str | None) -> int:
    """Import the merged food tables, flagging rows whose arithmetic disagrees."""
    from app.services.food_import import import_dataset

    if not path.is_file():
        print(f"No such file: {path}")
        return 2

    async with SessionFactory() as session:
        report = await import_dataset(session, path, only_source=only)

    print(f"\n{report.summary()}")
    if report.skipped_incomplete:
        # Named, not just counted. "548 rows were dropped" is a number nobody can
        # act on; a list of names is something a person can go and fix.
        print(
            f"\n{report.skipped_incomplete} rows had no kcal, protein, carbohydrate "
            f"or fat and were not imported. A row missing one of those cannot be "
            f"logged, and importing it as a half-food only moves the failure to "
            f"the moment somebody tries to eat it. First 15:"
        )
        for name in report.incomplete_names[:15]:
            print(f"    {name}")
    if report.flagged:
        print(
            f"\n{report.flagged} rows state an energy their own macros contradict. "
            f"They were imported unchanged and filed for verification — open "
            f"/admin and check them against the printed table."
        )
    await engine.dispose()
    return 0


async def _apply_portions(*, replace: bool) -> int:
    """Attach curated portions to imported rows."""
    from app.services.portions_maghreb import WANTED, apply_portions

    async with SessionFactory() as session:
        counts = await apply_portions(session, replace=replace)

    print(
        f"\n{counts['foods_given_portions']} foods given portions "
        f"({counts['portions_added']} portions), "
        f"{counts['already_had_portions']} already had some "
        f"{'(replaced)' if replace else '(left alone — pass --replace to overwrite)'}"
    )
    print(
        "\nStill without a portion, deliberately. Every one of these varies by "
        "bakery, region or household and I have no source for a weight — a "
        "plausible number here would be an invented one:"
    )
    for item in WANTED:
        print(f"    {item}")
    await engine.dispose()
    return 0


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

    # Before any HTTPS call. The seeder talks to USDA, and on a machine with TLS
    # interception certifi cannot verify the response — which surfaced here as a
    # bogus "USDA rate limit" message. See core/tls.py.
    use_system_trust_store()

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

    if args[0] == "find-photos":
        if len(args) < 2:
            print("Usage: python -m app.cli find-photos <directory>")
            return 2
        return _find_photos(Path(args[1]))

    if args[0] == "import-picks":
        if len(args) < 2:
            print("Usage: python -m app.cli import-picks <picks.json>")
            return 2
        return asyncio.run(_import_picks(Path(args[1])))

    if args[0] == "import-foods":
        if len(args) < 2:
            print(
                "Usage: python -m app.cli import-foods <dataset.json> "
                "[--only INNTA|Ciqual|FoodDataCentral]"
            )
            return 2
        only = args[args.index("--only") + 1] if "--only" in args else None
        return asyncio.run(_import_foods(Path(args[1]), only))

    if args[0] == "apply-portions":
        return asyncio.run(_apply_portions(replace="--replace" in args))

    print(f"Unknown command: {args[0]}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
