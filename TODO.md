# CalAi — what is left to do

Rewritten 3 August, updated 5 August and 26 September 2026. Every number below
was checked against the code or a live query, not recalled.

**Where the app stands:** 674 backend tests (≈5 minutes — see Known thin spots), `ruff` clean, `tsc` clean,
`alembic check` clean, the Expo bundle builds. One Postgres (Supabase) plus Redis
for rate-limit counters. **410 foods**, of which 189 are Tunisian (INNTA) and 35
are curated with photographs; 176 portions. 5 accounts, 23 diary entries — so it
is being used, lightly, by its author.

**What it is:** a calorie tracker for **Tunisia first**, then Algeria, Morocco and
Egypt. That is the sentence everything below now has to serve, and it is the one
thing the old list never said.

---

## ✅ Fixed 26 September

- **The hand-built auth is shut while Supabase is configured.** Every
  `/api/v1/auth/*` route answers 404 and a `SECRET_KEY`-signed token is refused.
  `/register` was a live lockout: one POST claimed a stranger's address without
  confirming it, and their own Supabase sign-up was refused from then on.
- **Signing in no longer writes on every request.** `_provision` INSERTed and
  COMMITted each time — three round trips, ~250 ms against eu-north-1 (measured
  84 ms each) — before the endpoint did any work. It now reads first and writes
  only for a new account. The home screen sends six requests per visit.
- **The embedding search experiment is stashed, not merged** (`git stash list`).
  `text-embedding-004` answers 404, so it fell back silently to a character hash
  with no meaning, made one sequential call to Google per unseen food name, sent
  the key in the URL, re-sorted results by that score instead of the curated-first
  tier, and made the test suite call Google for real (4.5× slower).
- **The seven bundled photos went from 5.7 MB to 1.3 MB.** Same 1024 px, JPEG
  quality 82; the previous files were saved near-lossless. All now under the
  300 KB that `assets/photos/README.md` asks for.
- **The 503 message names Supabase**, not only `docker compose up -d`.

---

## ✅ UI audit, 27 September

Every screen and shared component read; `tsc` clean and a production Android
bundle built afterwards. **Not yet looked at on a device** — the list under
"Check on the phone" is what to watch.

- **Contrast.** Accent `#6366F1` → `#4F46E5` (white on it 4.47 → 6.3:1). New
  `*Text` tokens for coloured words: carbs-on-carbs-tint was 1.9:1. Inactive
  tab labels and week letters moved off `inkFaint` (2.2:1). Danger split from
  protein's red. Legacy `clay`/`clayDeep`/`inkWash`/`paper` aliases deleted.
- **Hard-coded English.** Scan review (nearly all of it), macro tiles
  ("left"/"over"), "Loading…", servings, the partial-nutrients note, "Forgot
  your password?", the password hint, the search footnote, six a11y labels.
- **French decimals.** Weight, food amount and scan grams used `Number()`, so
  "72,5" from a French keypad was refused. `parseDecimal` in `lib/units.ts`.
- **Real bugs.** Scan logged to today whatever day was open. Scan's pinned
  footer was absolutely positioned — edge to edge, in the home-indicator area.
  A failed multi-item log threw the scan away. The + button's hitSlop stole
  taps from the Profile tab; water +ml buttons overlapped. The weekly target
  line was drawn against the wrong height. BMI gradient stops were at 33/66%
  instead of the real band edges, so "overweight" sat on green. Projection
  chart dots were half-clipped. Catalogue sheet ignored the home-indicator
  inset. Food source said "innta"/"ciqual" raw. Text fields jumped on focus.
- **Improvements.** Pull to refresh and a Retry button on Home and Progress.
  Search keeps results while typing instead of flashing them away. Food
  screen: back button, Log button pinned. Ruler picker operable by
  VoiceOver/TalkBack. Metric first in unit toggles. Nothing under 11px.

### Check on the phone

The sign-in hero (now full bleed), the scan review footer, the Progress week
bars, and the BMI card are the four layouts changed most by reasoning alone.

### UI still open

- Deleting a diary entry is long-press only, with nothing on screen saying so.
- Settings renders nothing where the targets card goes until the profile loads.
- Numbers format by *device* locale, not the app's language ("1.5 L" in French).
- The + menu does not close on Android's back button.
- `@expo-google-fonts/fraunces` is a dependency nothing imports.

---

## 1. The admin console is plain and feels slow

*(A Notes tab now exists: database counts, the serving sizes still wanted, and
every food by name with a `no-photo` filter — the working list for the next
shoot. The performance points below still stand.)*

`/admin` works and every decision goes through the API, which was the point. What
it is not is pleasant, and two of the reasons are measurable rather than
aesthetic.

**Why it feels slow, actually.** Nothing here is a rendering problem.

- Every refresh fetches **both** queues, including the tab you cannot see. One
  decision therefore costs four round-trips: two to act and re-read, two more for
  a list nobody is looking at.
- Those round-trips go to Supabase in **eu-north-1**. From a laptop that is tens
  of milliseconds per query and several queries per action, and it is felt.
- There is no optimistic update. The card sits there looking untouched until the
  whole cycle returns, which reads as "did my click register?" — the exact
  feeling that makes people click twice.

**What to do, in order of effect:**

1. Fetch only the visible tab; keep the other tab's count from the last load.
2. Remove the decided card immediately and reconcile on the response, so the
   list responds at the speed of the click rather than the speed of Stockholm.
3. A real pending state on the buttons, not just `disabled`.
4. Then the look: proper type scale, spacing, a keyboard shortcut for
   approve/reject, and the macro cross-check given more visual weight — it is the
   most useful thing on the card and currently reads as a footnote.

Keep two things through any rewrite: **the macro cross-check** (4/4/9 against
declared calories, flagged past 10%) and **`correctable`** on the API response,
which is what hides the correction form for USDA and Open Food Facts rows instead
of offering it and then refusing with a 422.

---

## ✅ 2. Tunisian food data — imported

**189 INNTA foods are live on Supabase**, searchable in the app. 39 rows were
refused for missing one of kcal/protein/carbohydrate/fat; 9 were imported
unchanged and flagged for a human.

    python -m app.cli import-foods <dataset.json> [--only INNTA]
    python -m app.cli apply-portions

Four things the dataset turned out to need, each found by looking rather than by
trusting:

- **INNTA's English names are OCR wreckage** — `5EMOLINA FLOUR`, `POTATOE5, RAW`,
  and for cabbage `~ f'- ' CASSAGE, GREEN, RAW`. 23 of 155 visibly damaged. The
  importer discards the English column entirely and shows the clean French name
  to English users. An untranslated name is honest; a mangled one is broken.
- **`œ` has no Unicode decomposition**, so a naive fold turns `œuf` into `uf`.
  The egg portions matched nothing at all on the first run, silently.
- **Fibre is ~2 kcal/g, not 4.** These tables give carbohydrate by difference,
  which includes fibre, so a flat 4 flagged raw spinach and mushroom as broken
  when they were fine.
- **Portion matching by name cannot be trusted.** Substring matching gave
  *Bonbons, sucreries* a sugar cube; word boundaries still gave *Pomme de terre*
  "1 apple = 182 g" and *Yaourt aux fruits* a 206 g glass of milk. Every veto in
  `portions_maghreb.PORTIONS` is a wrong match that actually happened.

### Still wanted from the dataset

- **Serving sizes.** Eight foods have none and will not get an invented one:
  tabouna, mlawi, malsouka, bsissa, harissa, rayeb/leben, chamia, makroud. They
  are listed in `WANTED`, printed by `apply-portions`, and shown in the admin
  console's Notes tab. A kitchen scale settles all eight.
- **Tunisian dishes.** INNTA is an ingredient table. brik, lablabi, ojja,
  mechouia, merguez and makroud are all absent, and those are what people
  actually log. 228 rows of raw ingredients is a foundation, not the product.
- **Arabic.** Zero rows in 4,021. Names are data like `name_fr` and would be
  easy; an Arabic *interface* is right-to-left and touches the whole app. Worth
  deciding which before starting.
- **Ciqual's 3,430 rows** are still unimported, deliberately — the ranking that
  keeps French dishes from crowding out Tunisian ones now exists, so they can
  come in whenever.

---

## ✅ 3. USDA is out of the way

Search is curated-first. `pain` returns six Tunisian breads and no USDA at all;
`quinoa` — which nothing curated matches — returns two USDA rows renamed from
laboratory form. Default results dropped from 25 to 6.

Ranking: catalogue → INNTA → your own foods → Ciqual → USDA/Open Food Facts.

Three things to keep if this is ever rewritten:

- **USDA is absent, not ranked lower**, whenever anything curated matches. Half
  a list of Tunisian food and half laboratory names is still the confusing list.
- **`browse_search` and `search_foods` are two functions on purpose.** Photo
  scanning uses the second and must keep full USDA access — its candidates are
  never shown to anybody, only the winner's numbers reach the screen. One
  function with a flag would eventually get the flag wrong.
- **`readable_name` renames, never renumbers.** No nutrition value, source or id
  is touched, and it only ever runs on USDA and Open Food Facts rows.

### The gap this leaves

Imported foods are **searchable but not browsable**. The Ingredients screen shows
only the 35 curated entries with photographs, so a user has to know to type
"tabouna". Closing that means promoting Tunisian staples to catalogue entries —
a slug, a category and a photo each. Probably 30–40 of them, not all 189.

---

## ✅ Fixed from correction.txt (5 August)

Three were real bugs, and two of them were invisible from the code alone:

- **"Couldn't identify those foods."** The text path sent `thinkingBudget: 0`;
  both current Gemini models answer `400 INVALID_ARGUMENT` to a zero budget, so
  every described meal failed. Only the text path sent zero, which is why photo
  scanning kept working. See `TEXT_THINKING_BUDGET_TOKENS`.
- **The keyboard's Search key did nothing.** `returnKeyType="search"` with no
  `onSubmitEditing` — it did not even dismiss the keyboard.
- **Clearing the amount field emptied the food screen.** An invalid quantity made
  `scaled` null, and the guard below reads null as "still loading", so deleting
  three characters replaced the food with the word "Loading…".

Also: back buttons on four dead-end screens and the recipe error state; delete
account (typed-email confirmation, approved contributions detached rather than
cascaded); language chips given equal heights and a full tap target; and the
oversized kcal numbers given a line height to match — `text.numeric` carries
`lineHeight: 20` for 14pt text and four screens overrode only the font size,
clipping the digits.

**Left as a decision, not done:** a photograph for the dashboard figure. The slot
exists (`imagery.bodyFigure`, drawn figure as fallback) but one photo is one
body, and the current figure is drawn from the user's own height and weight.
Doing it properly means one image per BMI band.

---

## Also still missing

Ordered by what would hurt most to leave.

### One line, real consequence

- **There is no git remote.** The only copy of this project, history included,
  is one laptop disk. A private GitHub repository is one command.
- **`REDIS_URL` is not set.** The shared rate limiter exists and is not switched
  on; counters are per-process and nothing says so at a glance.
- **Email confirmation is off in Supabase.** Anyone can register on an address
  they do not own, and that address is the password-reset channel. Dashboard
  toggle, no code.

### Genuinely unbuilt

- **No mobile tests at all.** 663 backend tests, zero on the client. 484
  translated strings and every screen ride on `tsc` alone. Add `jest-expo`
  deliberately — do **not** run `expo lint`, which previously bootstrapped an
  unwanted ESLint config into this project.
- **Email is not production-ready.** Supabase sends the reset and confirmation
  mail now, not `services/email.py` — but through its built-in mailer, which is
  for trying things out and heavily rate limited. Custom SMTP (Resend, Postmark)
  in the dashboard, then turn email confirmation on.
- **Delete the hand-built auth.** It is shut in production but still the way
  ~25 test files sign in. Move them onto Supabase-style tokens — the fake-JWKS
  fixture in `test_supabase_login.py` is most of the work — then delete
  `api/v1/auth.py`, the HS256 half of `core/security.py` and `get_current_user`'s
  fallback, and drop `refresh_tokens` and `password_reset_tokens` in a migration.
- **Typo-tolerant search.** "tabona" should find tabouna. The right tool is
  Postgres's `pg_trgm` — a migration and a GIN index, no network — not the
  stashed embedding experiment. Keep ranking by `SEARCH_TIER` first.
- **No builds, no deployment.** Expo Go on SDK 54 only, so nobody outside this
  machine has run the app. `mobile/AGENTS.md` forbids upgrading Expo/React Native
  until this changes.
- **The plan screen is still English inside a French app.** `targets.py` sends
  prose — about ten derivation steps and the warnings. The fix is the API
  returning keys and params instead of sentences; roughly an hour, and it changes
  the response schema.
- **Dark mode. Offline support.** Real features, nobody blocked on them.

### Known thin spots

- Nobody has watched `/report/[id]`, `/reports` or `/photo-credits` render on a
  device. They typecheck and their endpoints answer; that is all.
- The admin console's JavaScript is checked by `node --check` and nothing else.
  There is no browser in the test suite.
- `FoodThumb`'s image-error fallback has never run.
- Runtime language switching is wired and unverified.
- The README's phase table predates the catalogue, meals, photos, the pace
  picker, i18n, moderation and reporting.
- The test suite takes ~5 minutes; the README's 21 seconds is long gone. Run
  `pytest --durations=20` before guessing why — a test reaching the network
  with the real keys in `.env` is the first suspect, as it was for embeddings.
- The last two commits bundle 170 files under one generic message each, which
  makes `git bisect` and review useless across them. Back to one change per
  commit.

---

## Suggested order

0. **A git remote.** Everything below is worth less while it exists on one disk.
1. **The 9 flagged foods**, in `/admin` with the INNTA table open. Fifteen
   minutes, and they are wrong numbers sitting in a live database.
2. **The 8 serving sizes**, with a kitchen scale. Nobody logs 100 g of tabouna.
3. **Tunisian foods on the browse screen** — a slug, a category and a photo for
   30–40 staples. Right now a user has to know to search "tabouna".
4. **Admin console polish (1)** — small, and you are its only user.
5. **A mobile test runner** — cheap now, expensive later.
6. **An email provider**, then **builds and deployment**.
7. **Ciqual's 3,430 rows**, whenever — the ranking to hold them in place exists.

---

## The rule that governs all of it

> **Never invent, estimate, or hardcode a nutrition value. Not once. Not as a
> placeholder.**

This is why the catalogue was empty rather than pre-filled with plausible
numbers, why the AI is asked only for food names and grams, why a missing
nutrient renders as an em dash instead of `0 g`, and why an upheld report against
a USDA row withdraws it rather than letting an admin retype its calories.

It applies to the Tunisian data too. Real measured values with a source, or the
field stays blank.
