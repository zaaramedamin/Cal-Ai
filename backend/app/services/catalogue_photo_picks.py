"""Gathering catalogue photo candidates, and a contact sheet to choose from.

The search terms below are the part that cannot be automated. Each line is a
judgement about what the food looks like when somebody is about to log it —
cooked where it is eaten cooked, whole where it is eaten whole.

They are also short, which is not a stylistic choice. Commons ANDs every term, so
a descriptive query fails silently: `avocado halved fruit` returns **zero**
results, and reads exactly like Commons having no avocados. Two words is about
the limit before a query starts excluding the thing it describes. Anything longer
relies on `search_broadening` to cut it back down.

The output is an HTML file opened in a browser. Ten thumbnails per food, click
one, and the choice is written to `picks.json` for the importer to read. Thirty
five foods takes a couple of minutes, and every photograph that ships was looked
at by a person first.
"""

import json
import logging
from pathlib import Path

from app.services.photo_sources import Candidate, download, search_broadening

logger = logging.getLogger(__name__)

#: Search terms per catalogue slug. Written to describe the food *as eaten*.
QUERIES: dict[str, str] = {
    # Noun first, qualifier second. `search_broadening` drops words from the
    # right when a query is too tight, so the head of each line is the word that
    # must survive.
    #
    # Protein — cooked where cooked is the state anyone logs.
    "chicken-breast": "chicken breast grilled",
    "egg": "boiled egg",
    "salmon": "salmon fillet cooked",
    "tuna-canned": "canned tuna",
    "beef-mince": "minced beef",
    # Not "tofu": that returns mapo tofu, tofu sisig and miso soup — cooked
    # dishes, every one. "silken" is the word that finds a plain block.
    "tofu": "silken tofu",
    "lentils": "lentils cooked",
    "chickpeas": "chickpeas cooked",
    # Carbs
    "rice-white": "rice bowl cooked",
    "pasta": "spaghetti cooked",
    "bread": "bread sliced",
    "oats": "oats rolled",
    "potato": "potatoes raw",
    "sweet-potato": "sweet potato",
    # Fruit — whole and unstyled. A fruit salad is a different food.
    "banana": "bananas bunch",
    "apple": "apple red",
    "orange": "orange citrus",
    "strawberries": "strawberries fresh",
    "blueberries": "blueberries fresh",
    "avocado": "avocado halved",
    # Vegetables
    "broccoli": "broccoli florets",
    "tomato": "tomatoes fresh",
    "carrot": "carrots fresh",
    "spinach": "spinach leaves",
    "bell-pepper": "bell peppers",
    "cucumber": "cucumber fresh",
    # Dairy
    # Emphatically not "milk glass", which is an antiques category — opaque
    # white pressed glassware, with far more photographs on Commons than the
    # drink has. All six results were vases and compotes.
    "milk": "glass milk drink",
    # "yogurt bowl" finds breakfast bowls with fruit and granola on top.
    "greek-yoghurt": "plain yogurt",
    "cheddar": "cheddar cheese",
    "butter": "butter dairy",
    # Drinks
    "orange-juice": "orange juice glass",
    "coffee": "coffee cup black",
    # Fats
    "olive-oil": "olive oil bottle",
    "peanut-butter": "peanut butter",
    "almonds": "almonds nuts",
}


def gather(slugs: list[str], per_food: int = 10) -> dict[str, list[Candidate]]:
    """Search Commons for each slug. Missing slugs are reported, not raised."""
    results: dict[str, list[Candidate]] = {}
    for slug in slugs:
        query = QUERIES.get(slug)
        if query is None:
            logger.warning("No search term for %r — skipping", slug)
            continue
        found = search_broadening(query, limit=per_food)
        results[slug] = found
        logger.info("%s: %d candidates", slug, len(found))
    return results


def write_contact_sheet(
    results: dict[str, list[Candidate]], destination: Path, names: dict[str, str]
) -> Path:
    """Write a self-contained HTML picker. Returns the file path.

    Self-contained because the alternative is running a server to choose
    photographs, and the choice is a one-off.
    """
    payload = {
        slug: [
            {
                "title": c.title,
                "thumb": c.thumb_url,
                "page": c.descriptor_url,
                "license": c.license,
                "artist": c.artist,
                "credit": c.credit,
            }
            for c in candidates
        ]
        for slug, candidates in results.items()
    }

    html = _SHEET.replace("__DATA__", json.dumps(payload)).replace(
        "__NAMES__", json.dumps(names)
    )
    destination.write_text(html, encoding="utf-8")
    return destination


def fetch_picked(picks: dict[str, dict]) -> dict[str, tuple[bytes, dict]]:
    """Download the chosen image for each slug.

    Returns `{slug: (jpeg_bytes, attribution_fields)}`, skipping any download
    that fails so one dead URL cannot cost you the other thirty-four.
    """
    fetched: dict[str, tuple[bytes, dict]] = {}
    for slug, pick in picks.items():
        try:
            data = download(pick["thumb"])
        except Exception as exc:  # noqa: BLE001 - report and continue
            logger.warning("%s: download failed (%s)", slug, exc)
            continue
        fetched[slug] = (
            data,
            {
                "source_url": pick.get("page") or None,
                "license": pick.get("license") or None,
                "attribution": pick.get("credit") or None,
            },
        )
    return fetched


_SHEET = """<meta charset="utf-8">
<title>CalAi — pick catalogue photos</title>
<style>
  body { font: 15px/1.5 -apple-system, Segoe UI, sans-serif; margin: 0; padding: 24px;
         background: #f6f6f4; color: #14140f; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .lede { color: #6b6b63; margin: 0 0 24px; max-width: 60ch; }
  section { margin-bottom: 28px; background: #fff; border-radius: 14px; padding: 16px; }
  h2 { font-size: 15px; margin: 0 0 2px; }
  .slug { font: 12px ui-monospace, monospace; color: #9a9a90; }
  .row { display: flex; gap: 10px; overflow-x: auto; padding: 12px 0 4px; }
  figure { margin: 0; flex: 0 0 150px; cursor: pointer; }
  img { width: 150px; height: 150px; object-fit: cover; border-radius: 10px;
        border: 3px solid transparent; display: block; background: #eee; }
  figure.on img { border-color: #1f7a4d; }
  figcaption { font-size: 10px; color: #8a8a80; margin-top: 4px; line-height: 1.3;
               overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3;
               -webkit-box-orient: vertical; }
  .none { color: #b04a3a; font-size: 13px; }
  #bar { position: sticky; bottom: 0; background: #14140f; color: #fff; padding: 14px 18px;
         border-radius: 12px; display: flex; align-items: center; gap: 16px; margin-top: 24px; }
  button { font: inherit; background: #fff; color: #14140f; border: 0; border-radius: 8px;
           padding: 9px 16px; cursor: pointer; font-weight: 600; }
  #out { width: 100%; height: 160px; margin-top: 12px; font: 11px ui-monospace, monospace;
         display: none; }
</style>
<h1>Pick a photograph for each food</h1>
<p class="lede">Click one image per food. Only freely-licensed images are shown &mdash;
public domain, CC0, CC BY and CC BY&#8209;SA. When you are done, press Copy and paste
the result into <code>picks.json</code>.</p>
<div id="app"></div>
<div id="bar">
  <span id="count">0 chosen</span>
  <button onclick="copyPicks()">Copy picks</button>
  <button onclick="document.getElementById('out').style.display='block'">Show JSON</button>
</div>
<textarea id="out" readonly></textarea>
<script>
const DATA = __DATA__, NAMES = __NAMES__, picks = {};

document.getElementById('app').innerHTML = Object.entries(DATA).map(([slug, list]) => `
  <section>
    <h2>${NAMES[slug] || slug}</h2>
    <div class="slug">${slug}</div>
    ${list.length ? `<div class="row">${list.map((c, i) => `
      <figure data-slug="${slug}" data-i="${i}">
        <img src="${c.thumb}" loading="lazy" alt="">
        <figcaption>${c.license} &middot; ${c.artist}</figcaption>
      </figure>`).join('')}</div>`
      : '<p class="none">No usable candidates. Photograph this one yourself.</p>'}
  </section>`).join('');

document.getElementById('app').addEventListener('click', (e) => {
  const fig = e.target.closest('figure');
  if (!fig) return;
  const slug = fig.dataset.slug;
  document.querySelectorAll(`figure[data-slug="${slug}"]`).forEach(f => f.classList.remove('on'));
  fig.classList.add('on');
  picks[slug] = DATA[slug][+fig.dataset.i];
  render();
});

function render() {
  const n = Object.keys(picks).length;
  document.getElementById('count').textContent =
    `${n} of ${Object.keys(DATA).length} chosen`;
  document.getElementById('out').value = JSON.stringify(picks, null, 2);
}

function copyPicks() {
  const text = JSON.stringify(picks, null, 2);
  navigator.clipboard.writeText(text).then(
    () => { document.getElementById('count').textContent = 'Copied to clipboard'; },
    () => { document.getElementById('out').style.display = 'block'; }
  );
}
render();
</script>
"""
