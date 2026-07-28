# CalAi — what is left to do

Written 28 July 2026. Every claim here was checked against the codebase, not
recalled — counts come from `grep`, database numbers from a live query, test
totals from a real run.

**Where the project stands right now:** 408 backend tests passing, `ruff` clean,
`tsc` clean, working tree clean. The eight items from the last brief are built.
What follows is what is *not* built, what is half-built, and what is quietly
wrong.

Ordered by what blocks the most.

---

## 🔴 Blocker — nothing works properly until this is done

### 1. Get a real USDA API key

**This is the single highest-value thing on the list, and it takes two minutes.**

The catalogue database is **empty**. Verified just now:

```
food_items:        0
meals:             0
catalogue_photos:  0
```

`.env` still holds `USDA_API_KEY=DEMO_KEY`, which allows 30 requests an hour.
Seeding 35 foods needs more than that in one pass, so the seeder stops partway
and reports honestly rather than filling in blanks.

**What is broken until this is fixed:**

| Feature | State without a key |
|---|---|
| Ingredients browse screen | Shows "the catalogue is empty" |
| Meal builder | Nothing to add — every ingredient 422s |
| Catalogue photos | Import works, but no food document to attach them to |
| Food search | Works, but rate-limited and the matcher looks worse than it is |
| Meal suggestions | Thin, for the same reason |

**Fix:**

```powershell
# 1. Free key, no card: https://fdc.nal.usda.gov/api-key-signup.html
# 2. Paste into .env as USDA_API_KEY=...
cd C:\dev\calai\backend
.\.venv\Scripts\python.exe -m app.cli seed-catalogue
```

The seeder is resumable and idempotent, so running it twice is safe.

---

## 🟠 Half-finished — visible to the user

### 2. Finish the French translation

The infrastructure is complete and the type system enforces it: a key added to
English without French **fails the build** (verified by deliberately adding one).
Food names live on the catalogue documents as `name_en`/`name_fr` and are already
bilingual, so the data side is done.

What remains is mechanical. Measured per file — `t()` means the file uses the
translation hook, the number is remaining English-looking literals:

| File | Hook | English literals left |
|---|---|---|
| `app/(auth)/forgot-password.tsx` | — | 5 |
| `app/(auth)/reset-password.tsx` | — | 8 |
| `app/(tabs)/progress.tsx` | — | 3 |
| `app/plan.tsx` | — | 9 |
| `app/recipes.tsx` | — | 4 |
| `features/recipes/recipe-builder.tsx` | — | 5 |
| `app/onboarding.tsx` | `t()` | 15 |
| `app/scan.tsx` | `t()` | 12 |
| `app/food/[id].tsx` | `t()` | 7 |
| `app/(tabs)/settings.tsx` | `t()` | 6 |
| `app/search.tsx` | `t()` | 4 |
| `app/(tabs)/index.tsx` | `t()` | 2 |
| `components/funnel.tsx` | — | 1 |
| `components/wordmark.tsx` | — | 1 |

**Fully done:** login, register, catalogue, meals, meal-builder, amount-stepper,
body-avatar, auth-form.

Roughly **80 strings** left. Onboarding is the biggest single win — it is the
first thing a new user reads, and 15 of its strings are still English.

**One thing to be careful about:** French pluralises verbs, not just nouns.
`meals.missingOne` / `meals.missingMany` are separate strings for that reason —
do not "simplify" them into one string with an `s` suffix.

### 3. Onboarding still describes the old calorie model

`GOAL_OPTIONS` in `onboarding.tsx` reads:

- Lose fat → *"20% below maintenance"*
- Lean bulk → *"10% above maintenance"*
- Bulk → *"15% above maintenance"*

**Those percentages no longer set the target.** The pace picker does. The
descriptions are now describing a calculation the app does not perform, which is
exactly the drift the derivation system exists to prevent. Rewrite them to
describe the *goal* ("steady fat loss") and let the pace step own the numbers.

### 4. Photos are imported but nothing has been shot

The pipeline is built, tested and verified end to end. Nothing is stored:
`catalogue_photos: 0`. The synthetic test images were deleted deliberately.

Once the catalogue is seeded:

```powershell
# Name each file after its slug: chicken-breast.jpg, egg.jpg, milk.jpg
.\.venv\Scripts\python.exe -m app.cli import-photos C:\path\to\photos
```

The 35 slugs are listed in `backend/app/services/catalogue_seed.py`.

---

## 🟡 Architectural debt — decided but not delivered

### 5. Finish the MongoDB migration (item 2, half done)

Currently split across two databases:

| Postgres | MongoDB |
|---|---|
| `users`, `refresh_tokens`, `password_reset_tokens` | `food_items` |
| `user_profiles`, `weight_entries` | `meals` |
| `foods`, `food_portions` | `catalogue_photos` |
| `diary_entries` | |
| `recipes`, `recipe_ingredients` | |

The catalogue was built directly on Mongo so it would not need writing twice.
Everything else still needs moving.

**This is the riskiest item on the list** and I would not rush it. It moves data
people are already relying on, and Mongo has no foreign keys — so every
`ON DELETE SET NULL` guarantee has to become application code. The nutrient
snapshot on `diary_entries` already carries most of that weight, but the
migration needs to be written, tested and reversible before it runs anywhere
real.

Worth asking honestly before starting: **what is this migration buying?** The
catalogue genuinely suits documents. A diary of typed, related, transactional
rows does not, and Postgres is doing that job well. Moving it is a real cost for
no obvious gain — it may be worth keeping the split rather than finishing it.

### 6. `MEAL_LABELS` is dead code

Marked `@deprecated` in `mobile/src/api/diary.ts`. No screen imports it any more.
Delete it once nothing references it.

---

## 🔵 Never built — features named but absent

### 7. Barcode scanning (Open Food Facts)

`off_user_agent` sits in `config.py` and `.env.example`. **There is no
implementation** — no client, no endpoint, no screen. Confirmed by grep: the
config value is the only mention of Open Food Facts in the whole backend.

This was in the original brief as a Phase 3+ item. It is the biggest missing
*feature*, as opposed to missing polish.

### 8. Dark mode

The app is light-only. `_layout.tsx` hardcodes `<StatusBar style="dark" />` and
nothing reads `useColorScheme()`. The design tokens are centralised in
`theme/tokens.ts`, so this is a tractable job — but every colour is currently a
literal light value, so it is not a small one either.

### 9. Offline support

Every screen requires the network. Noted in `auth/context.tsx`: opening the app
with no signal currently logs you out. There is no local cache and no write
queue.

---

## ⚫ Production readiness — nothing here is safe to deploy yet

### 10. Rate limiting is per-process

`core/rate_limit.py` keeps counters in memory. Two uvicorn workers means two
independent budgets, and every restart resets them. It protects against a single
misbehaving client on one box; it does not protect the shared USDA and Gemini
quotas in any real deployment. Needs Redis.

### 11. No email provider

`services/email.py` logs reset links to the console. Password reset therefore
does not work for a real user on a real device — they never receive the link.
The module is a single seam, so adding a provider changes one file.

### 12. CORS is wide open

`main.py` allows `*` in development. There is a comment saying an explicit origin
list is required before deploying. It has not been written.

### 13. Secrets and config

- `SECRET_KEY` rotation invalidates every token at once — fine, but there is no
  key-rotation procedure written down.
- `GEMINI_API_KEY` is set in `.env` and works. `GEMINI_MODEL` defaults to
  `gemini-flash-lite-latest` deliberately: the stronger `gemini-flash-latest`
  alias resolves to a model with a **20 request/day** free tier, which is what
  caused the "scanning limit reached" bug. Do not "upgrade" it without a paid
  key.

### 14. No builds, no deployment

Phase 7 in the README covers this and is untouched. The app runs in Expo Go on
SDK 54 only. `mobile/AGENTS.md` explicitly forbids upgrading Expo/React
Native/React until the project moves to a development build.

---

## 🧪 Testing gaps

### 15. The mobile app has no test runner

408 backend tests, **zero mobile tests**. `tsc --noEmit` is the only automated
check.

The pure-logic modules are already written to be testable and are the obvious
place to start:

- `features/body/shape.ts` — BMI mapping, silhouette width, height damping
- `features/onboarding/pace.ts` — daily kcal, weeks-to-target, arrival dates
- `features/meals/draft-store.ts` — merging duplicates, live totals
- `lib/units.ts` — kg/lbs and cm/ft-in conversion
- `api/catalogue.ts` — `amountStep`, `formatAmount`, `unitSuffix`

I verified `shape.ts` and `pace.ts` by compiling them and running them by hand.
That found a real bug — the height mapping only varied 7% across 150–200 cm,
which nobody would notice — but it is not a substitute for a test.

**Caution:** `expo lint` previously bootstrapped an unwanted ESLint config into
this project. Add a runner deliberately (Jest via `jest-expo`), not by running a
command that offers to set one up.

### 16. Untested paths worth naming

- The photo `failed` branch in the CLI importer (unknown-slug check runs first,
  so a corrupt file never reaches it in practice).
- `FoodThumb`'s image-error fallback — no photo has ever loaded, so it has never
  run.
- Language switching at runtime — the picker is wired, but nothing verifies the
  whole tree re-renders.

---

## 📝 Documentation drift

### 17. The README roadmap is out of date

Phases 6 and 7 are unticked, but the table has no rows at all for the catalogue,
meals, photos, the pace picker, the body figure, i18n or MongoDB — all of which
now exist. Anyone reading the README gets a materially wrong picture of the
project.

### 18. `.env.example` is complete, but the setup story has grown

Section "3b. Seed the food catalogue" exists. It should say plainly that
`DEMO_KEY` **cannot** complete the seed, rather than leaving that to be
discovered.

---

## Suggested order

1. **USDA key + seed** — two minutes, unblocks five features
2. **Import photos** — needs (1) first
3. **Fix the onboarding goal descriptions** — small, and currently misleading
4. **Finish the French translation** — ~80 strings, start with onboarding
5. **Add a mobile test runner** — cheap now, expensive later
6. **Barcode scanning** — the largest genuinely missing feature
7. **Decide whether to finish the Mongo migration or keep the split**
8. Production items (10–14) — only when deployment is actually on the table

---

## The rule that governs all of it

> **Never invent, estimate, or hardcode a nutrition value. Not once. Not as a
> placeholder.**

This is why the catalogue is empty rather than pre-filled with plausible numbers,
why the AI is asked only for food names and grams, and why a missing nutrient
renders as an em dash instead of `0 g`. Anything added to this list must hold to
it.
