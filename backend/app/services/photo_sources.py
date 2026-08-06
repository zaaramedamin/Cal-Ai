"""Finding freely-licensed catalogue photographs on Wikimedia Commons.

This module **gathers candidates**. It does not choose one. That split is the
whole design, and it comes from watching the obvious approach fail: asking
English Wikipedia for the lead image of "Chicken as food" returns a photograph of
live chickens in a market, because an article's lead image illustrates the
*topic*, not the *prepared food* somebody is about to log 120 g of. A search
ranked by relevance does no better — the third hit for "chicken breast cooked" is
a family dinner with the caption still attached.

So the machine fetches ten plausible images per food and a human picks. The
picking is made cheap (a contact sheet in a browser, one click per food) rather
than eliminated, because eliminating it means shipping a photograph of live
chickens next to a nutrition label.

**Licences are filtered, not merely recorded.** Commons hosts plenty of images
this project cannot use:

- `NonCommercial` and `NoDerivatives` are disqualifying outright — this is a
  commercial app, and every image is re-encoded and cropped on import, which is a
  derivative work.
- GFDL-only is legally usable but demands the full licence text travel with the
  image. That is unreasonable in a phone app, so it is excluded rather than
  half-honoured. (An image dual-licensed GFDL *and* CC BY-SA is fine; the CC
  terms are the ones taken.)

What survives is public domain, CC0, CC BY and CC BY-SA. The last two require
attribution, which is why `Candidate` carries the artist and the licence all the
way through to a database column and onto the food's screen. An attribution that
stops at the import script is not attribution.
"""

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple

logger = logging.getLogger(__name__)

COMMONS_API = "https://commons.wikimedia.org/w/api.php"

#: Wikimedia asks for a descriptive User-Agent with a contact address and blocks
#: generic ones. This is a courtesy that is also a rate-limit avoidance measure.
USER_AGENT = "CalAi/0.1 (catalogue photo import; aminezaara67@gmail.com)"

#: Licence families this project can use. Matched against Commons'
#: `LicenseShortName`, lowercased.
ALLOWED = (
    "cc0",
    "cc by",
    "cc by-sa",
    "public domain",
    "pd-",
    "no restrictions",
)

#: Disqualifying regardless of anything else appearing alongside them.
FORBIDDEN = ("nc", "nd", "noncommercial", "no derivative")

#: Below this and the crop to 512px square would be an upscale.
MIN_EDGE = 600

#: Commons holds some enormous scans. Downloading one to make a 20 KB thumbnail
#: is wasted bandwidth, so ask for a scaled render instead of the original.
REQUEST_WIDTH = 1024


class Candidate(NamedTuple):
    """One possible photograph, with everything needed to credit it."""

    title: str
    """Commons file title, e.g. `File:Huevo frito.jpg`."""

    thumb_url: str
    """A scaled render, which is what actually gets downloaded."""

    descriptor_url: str
    """The Commons page. This is the attribution link a reader should land on."""

    license: str
    """Short name as Commons states it, e.g. `CC BY-SA 4.0`."""

    artist: str
    """Photographer, with Commons' HTML stripped back to a plain name."""

    width: int
    height: int

    @property
    def credit(self) -> str:
        """The one-line credit shown in the app."""
        return f"{self.artist} / Wikimedia Commons ({self.license})"


def licence_is_usable(short_name: str) -> bool:
    """Whether this project may ship an image under `short_name`.

    Conservative on purpose: an unrecognised licence is refused rather than
    assumed permissive. The cost of a false negative is one fewer candidate; the
    cost of a false positive is shipping someone's photograph without the right
    to do so.
    """
    text = short_name.lower()

    # Check the forbidden markers on token boundaries. A bare substring test
    # rejects "CC BY-ND" correctly but also rejects nothing else usefully — while
    # matching "nc" inside "Public Domain, no copyright noticed" by accident.
    tokens = re.split(r"[^a-z0-9]+", text)
    if any(bad in tokens for bad in ("nc", "nd")):
        return False
    if any(bad in text for bad in ("noncommercial", "no derivative")):
        return False

    return any(good in text for good in ALLOWED)


def _plain_text(html: str) -> str:
    """Commons returns artist fields as HTML. Reduce to a readable name."""
    without_tags = re.sub(r"<[^>]+>", " ", html)
    unescaped = (
        without_tags.replace("&amp;", "&").replace("&quot;", '"').replace("&#039;", "'")
    )
    return re.sub(r"\s+", " ", unescaped).strip()


def _get(params: dict[str, str], timeout: float) -> dict:
    url = f"{COMMONS_API}?{urllib.parse.urlencode({**params, 'format': 'json'})}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    _throttle()  # Searches share the budget with downloads: one host, one client.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.load(response)


def search(query: str, limit: int = 10, timeout: float = 30.0) -> list[Candidate]:
    """Ten or so usable candidates for `query`, best match first.

    Returns an empty list on any failure. A photo import that dies halfway
    through because one search timed out is worse than one that reports which
    foods it could not find.
    """
    try:
        payload = _get(
            {
                "action": "query",
                "generator": "search",
                # `filetype:bitmap` keeps out SVG diagrams and PDFs, which
                # otherwise rank well for food words and are never what is wanted.
                "gsrsearch": f"filetype:bitmap {query}",
                "gsrnamespace": "6",  # File:
                "gsrlimit": str(limit * 3),  # Over-fetch; most get filtered out.
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|size|mime",
                "iiurlwidth": str(REQUEST_WIDTH),
            },
            timeout,
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Commons search for %r failed: %s", query, exc)
        return []

    pages = payload.get("query", {}).get("pages", {})
    if not pages:
        return []

    # `generator=search` returns a dict keyed by page id, in arbitrary order. The
    # `index` field is the one that carries the ranking.
    ordered = sorted(pages.values(), key=lambda p: p.get("index", 1_000_000))

    found: list[Candidate] = []
    for page in ordered:
        candidate = _to_candidate(page)
        if candidate is not None:
            found.append(candidate)
        if len(found) >= limit:
            break
    return found


def _to_candidate(page: dict) -> Candidate | None:
    infos = page.get("imageinfo")
    if not infos:
        return None
    info = infos[0]

    if not info.get("mime", "").startswith("image/"):
        return None
    if min(info.get("width", 0), info.get("height", 0)) < MIN_EDGE:
        return None

    meta = info.get("extmetadata", {})
    licence = _plain_text(meta.get("LicenseShortName", {}).get("value", ""))
    if not licence_is_usable(licence):
        return None

    artist = _plain_text(meta.get("Artist", {}).get("value", "")) or "Unknown"

    # `thumburl` is the scaled render; it is absent when the file is already
    # smaller than the requested width, in which case the original is right.
    thumb = info.get("thumburl") or info.get("url")
    if not thumb:
        return None

    return Candidate(
        title=page.get("title", ""),
        thumb_url=thumb,
        descriptor_url=info.get("descriptionurl", ""),
        license=licence,
        artist=artist,
        width=info.get("width", 0),
        height=info.get("height", 0),
    )


def search_broadening(query: str, limit: int = 10, timeout: float = 30.0) -> list[Candidate]:
    """Search, dropping trailing words until something comes back.

    Commons ANDs every term, which makes a descriptive query fail in a way that
    looks like the food does not exist. `avocado halved fruit` returns **zero**
    results — not because Commons lacks avocados, but because no single file
    matches all three words. `avocado halved` returns plenty.

    Dropping from the right preserves the important word: the queries below are
    written noun-first, so `chicken breast grilled` degrades to `chicken breast`
    and then to `chicken`, never to `grilled`.
    """
    words = query.split()
    for cut in range(len(words), 0, -1):
        attempt = " ".join(words[:cut])
        found = search(attempt, limit=limit, timeout=timeout)
        if found:
            if cut < len(words):
                logger.info("Broadened %r to %r", query, attempt)
            return found
    return []


#: Minimum gap between requests to Wikimedia. Fetching thirty-five images back to
#: back earns an HTTP 429 and the message "your bot is making too many requests"
#: — which arrives *per image*, so an unthrottled import silently returns a
#: handful of photos and no explanation. Wikimedia asks for serialised requests
#: from a single client rather than a specific rate; a fifth of a second is well
#: inside that and costs seven seconds across the whole catalogue.
MIN_INTERVAL_SECONDS = 0.2

_last_request_at = 0.0


def _throttle() -> None:
    global _last_request_at
    wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def download(
    url: str,
    timeout: float = 60.0,
    max_bytes: int = 12 * 1024 * 1024,
    attempts: int = 3,
) -> bytes:
    """Fetch image bytes, refusing anything implausibly large.

    The cap matches `catalogue_photos.MAX_SOURCE_BYTES`, so a file that would be
    rejected on import is not downloaded in the first place.

    Retries on 429 and honours `Retry-After`. Wikimedia is a donated resource and
    a client that hammers it through a rate limit deserves the block it gets.
    """
    for attempt in range(1, attempts + 1):
        _throttle()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) > max_bytes:
                    raise ValueError(f"{int(declared) // 1024 // 1024} MB is too large")
                # Read one byte past the cap so an undeclared oversize body is
                # caught too.
                data = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == attempts:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if (retry_after or "").isdigit() else 2.0 * attempt
            logger.info("Rate limited; waiting %.0fs before retry %d", delay, attempt + 1)
            time.sleep(delay)
            continue

        if len(data) > max_bytes:
            raise ValueError("larger than the 12 MB limit")
        return data

    raise ValueError("rate limited")  # pragma: no cover - loop always returns or raises
