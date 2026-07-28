"""Maintenance commands.

    python -m app.cli seed-catalogue [--force]

Deliberately a plain argv switch rather than Typer or Click. There is one
command; a CLI framework would be a dependency and an abstraction earning their
keep against a single `if`.
"""

import asyncio
import logging
import sys

from app.db.mongo import close_client, ensure_indexes, food_items
from app.services.catalogue_seed import SEEDS, seed_catalogue


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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    args = sys.argv[1:]

    if not args or args[0] in {"-h", "--help"}:
        print(__doc__)
        return 0

    if args[0] == "seed-catalogue":
        return asyncio.run(_seed(force="--force" in args))

    print(f"Unknown command: {args[0]}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
