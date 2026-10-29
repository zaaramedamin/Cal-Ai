# CalAi

A calorie and macronutrient tracker built for Tunisia first, with Algeria, Morocco and Egypt to follow.
The user enters body measurements and a goal, receives daily calorie and macro targets, and logs meals
against them. Foods can be searched, built from catalogue ingredients in real units, or identified from a
photograph.

The project is a working prototype: a FastAPI backend, a PostgreSQL database hosted on Supabase, and a
React Native (Expo) mobile client.

## Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Nutrition data integrity](#nutrition-data-integrity)
4. [Repository layout](#repository-layout)
5. [Running locally](#running-locally)
6. [Testing](#testing)
7. [Deployment](#deployment)
8. [Design decisions](#design-decisions)
9. [Status and known limitations](#status-and-known-limitations)

## Features

- **Accounts.** Sign-up, sign-in and password reset through Supabase Auth.
- **Onboarding and targets.** Daily calories and macros derived from age, sex, height, weight, activity
  level, goal and chosen pace (Mifflin-St Jeor BMR, activity multiplier, goal adjustment).
- **Food search.** Tunisian foods first (INNTA composition table), then the curated catalogue, then
  Ciqual, USDA FoodData Central and Open Food Facts. Search results are ranked in that order.
- **Diary.** Entries are logged to meal slots with a daily summary, macro progress and weekly view.
- **Catalogue and meals.** Ingredients in natural units (litres of milk, eggs by the egg) with photographs,
  and saved meals composed from them.
- **Recipes.** Custom recipes with live nutrition totals.
- **Photo scanning.** A meal photograph is analysed to propose foods and portions, which the user reviews
  before anything is logged.
- **Progress.** Weight history, BMI, a projection toward the goal, and water tracking.
- **Moderation.** User-submitted foods and reports against existing foods are decided by an administrator
  through a web console served at `/admin`.
- **Languages.** French and English, selected from the device language.

## Architecture

| Layer | Technology |
|---|---|
| Mobile client | Expo SDK 54, React Native 0.81, React 19, TypeScript (strict), expo-router |
| API | FastAPI, Python 3.13, SQLAlchemy 2.0 (async), Pydantic v2 |
| Database | PostgreSQL 16 on Supabase; schema managed with Alembic |
| Authentication | Supabase Auth; the API verifies ES256 tokens against the project's published keys |
| External data | USDA FoodData Central, Open Food Facts, Google Gemini (photo and text identification) |
| Rate limiting | Per-IP and per-account counters, in memory or in Redis when `REDIS_URL` is set |

The mobile client never calls the data providers directly. All requests go through the API, which caches
results in Postgres, keeps provider keys out of the app bundle and stays within provider rate limits.

## Nutrition data integrity

No nutrition value in the application is estimated, generated or hardcoded. Every food row is imported
from a published source and keeps its `source` and `source_id`, so any figure on screen can be traced to
its origin. A nutrient a source does not report is stored as `NULL` and displayed as an em dash, never
as zero.

This constraint shapes the photo scanner. The vision model is asked only which foods appear on the plate
and roughly how many grams of each; its response schema has no field for calories. The names are matched
against the food database, which supplies every number, and the user confirms the portions before the
entry is saved.

## Repository layout

```
calai/
├── backend/
│   ├── app/
│   │   ├── api/v1/          route handlers
│   │   ├── core/            settings, dependencies, security, rate limiting
│   │   ├── db/              engine, session handling, ORM models
│   │   ├── nutrition/       target and macro calculations
│   │   ├── services/        USDA, Open Food Facts, Gemini, catalogue, food import
│   │   ├── schemas/         Pydantic request and response models
│   │   ├── admin/           single-page moderation console
│   │   └── cli.py           data import and maintenance commands
│   ├── alembic/versions/    database migrations
│   └── tests/
├── mobile/
│   └── src/
│       ├── app/             expo-router screens
│       ├── api/             HTTP client and endpoint modules
│       ├── components/      shared UI components
│       ├── features/        feature-specific components
│       ├── i18n/            French and English strings
│       └── theme/           design tokens
├── List of Foods/           combined food-composition dataset (INNTA, Ciqual, USDA)
├── docker-compose.yml       local Postgres and Redis
└── .env.example             every environment variable, documented
```

## Running locally

### Prerequisites

- Node.js 20 or later
- Python 3.13
- Docker Desktop (used for the local test database)
- A Supabase project (free tier is sufficient) for the database and authentication
- The Expo Go app on a phone, on the same Wi-Fi network as the computer

### 1. Configuration

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Paste the generated value into `.env` as `SECRET_KEY`, then set:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Supabase session pooler string, using the `postgresql+asyncpg://` scheme |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | Project Settings, API |
| `USDA_API_KEY` | Free key from fdc.nal.usda.gov (the default `DEMO_KEY` is heavily limited) |
| `GEMINI_API_KEY` | Optional. Without it the photo-scan endpoint reports that the feature is disabled |

The mobile app needs the same Supabase values. Create `mobile/.env`:

```
EXPO_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon key>
```

The anon key is designed to be public. The database password and `SECRET_KEY` must never appear in
`mobile/.env`.

### 2. Database

Apply the migrations to the configured database:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
```

To populate an empty database with food data:

```powershell
python -m app.cli seed-catalogue
python -m app.cli import-foods "..\List of Foods\all_foods_deduplicated.json" --only INNTA
python -m app.cli apply-portions
```

`seed-catalogue` needs a real `USDA_API_KEY`. The import commands write to whatever `DATABASE_URL`
points at, so check it first.

Note on Supabase connection strings: use the **session pooler** (port 5432, user `postgres.<ref>`). The
direct connection is IPv6-only on the free tier, and the transaction pooler (port 6543) is incompatible
with asyncpg's prepared statements.

### 3. Start the API

```powershell
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Check <http://localhost:8000/api/v1/health>; it should report `"db": "ok"`. Interactive API documentation
is at <http://localhost:8000/docs> in development, and the moderation console is at
<http://localhost:8000/admin> for accounts flagged `is_admin`.

The server must bind `0.0.0.0`. The default `127.0.0.1` is unreachable from a phone.

### 4. Start the mobile app

```powershell
cd mobile
npm install
npx expo start
```

Scan the QR code with Expo Go. The app derives the API address from the host that served the bundle and
uses port 8000, so it follows the computer's address if the network changes.

## Testing

The test suite runs against a local Postgres container and refuses to run against any other host, because
its fixtures create and truncate tables.

```powershell
docker compose up -d
docker compose ps                      # wait until both services report "healthy"
```

`TEST_DATABASE_URL` in `.env` must point at the container (see `.env.example`). Then:

```powershell
# Backend: tests and lint
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m alembic check     # models and migrations agree

# Mobile: strict type check
cd ..\mobile
npx tsc --noEmit
```

The full backend suite takes several minutes. For a quicker check, run a single file, for example
`pytest tests/test_supabase_login.py`.

### Troubleshooting on Windows

- **The phone cannot reach the API or load the bundle.** With WSL or Hyper-V installed, Expo may advertise
  a virtual adapter's address. Pin the Wi-Fi address (from `ipconfig`) and restart with a clean cache:

  ```powershell
  $env:REACT_NATIVE_PACKAGER_HOSTNAME = "192.168.1.124"
  npx expo start -c
  ```

- **The API is reachable from the PC but not the phone.** Allow inbound port 8000 on the private profile,
  from an elevated PowerShell:

  ```powershell
  New-NetFirewallRule -DisplayName "CalAi backend (8000)" -Direction Inbound `
    -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
  ```

- **Database connections are slow.** Use `127.0.0.1` rather than `localhost` in local URLs. On Windows,
  `localhost` resolves to IPv6 first and every new connection waits for that attempt to fail
  (measured: 2123 ms against 84 ms).
- **PowerShell blocks scripts.** Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
- **`python` opens the Microsoft Store.** Disable the `python.exe` app execution alias in Settings, Apps,
  Advanced app settings.
- **A free Supabase project looks like a database outage.** Projects pause after a week without traffic.
  Restore it from the dashboard.

## Deployment

The database and authentication already run on Supabase, so deployment consists of hosting the API and
building the mobile client against it.

### API

`render.yaml` at the repository root is a Render Blueprint for the API. In the Render dashboard choose
**New, Blueprint**, select this repository, and fill in the values it asks for. It configures:

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Build command | `pip install -e .` |
| Start command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/v1/health` |
| Python version | 3.13 |

Any other host that runs a Python 3.13 web process works with the same commands. Environment variables:

| Variable | Notes |
|---|---|
| `ENVIRONMENT` | `production`. Disables `/docs` and restricts CORS |
| `DATABASE_URL` | Supabase session pooler string |
| `SECRET_KEY` | A fresh random value of at least 32 characters |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | Same as local |
| `USDA_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL` | Provider credentials |
| `OFF_USER_AGENT` | Descriptive agent with a contact address, required by Open Food Facts |
| `REDIS_URL` | Optional. Required for correct rate limiting with more than one worker |
| `TRUST_PROXY_HEADERS` | `true` only behind a proxy that overwrites `X-Forwarded-For` |

Free-tier hosts stop idle services, so the first request after a pause is slow.

### Mobile client

Release builds are produced with Expo Application Services (EAS); the profiles are in `mobile/eas.json`.
`mobile/.env` is not uploaded to the build servers, so the three public variables are stored as EAS
environment variables instead:

```powershell
cd mobile
npm install -g eas-cli
eas login
eas init
eas env:create --environment preview --name EXPO_PUBLIC_API_URL --value https://<api-host> --visibility plaintext
eas env:create --environment preview --name EXPO_PUBLIC_SUPABASE_URL --value https://<project-ref>.supabase.co --visibility plaintext
eas env:create --environment preview --name EXPO_PUBLIC_SUPABASE_ANON_KEY --value <anon key> --visibility plaintext
eas build --platform android --profile preview
```

`eas init` cannot write to a TypeScript config, so add the project id it prints to `mobile/app.config.ts`
as `extra.eas.projectId`. The `preview` profile produces an APK that installs directly on Android. iOS
distribution requires an Apple Developer account.

In Supabase, add `calai://**` to **Authentication, URL Configuration, Redirect URLs** so password-reset
links open the installed app.

For a demonstration without a native build, run `npx expo start` with `EXPO_PUBLIC_API_URL` set to the
deployed API and open the project in Expo Go.

## Design decisions

- **FastAPI over Express.** Pydantic gives runtime validation and an OpenAPI schema from a single
  declaration, and the nutrition calculations are easier to test in Python.
- **One database.** Accounts, diary, recipes, the catalogue, saved meals and photographs all live in
  Postgres. A diary entry holds a real foreign key to the food it records, and `ON DELETE RESTRICT`
  prevents a saved meal from losing an ingredient and silently under-reporting its calories.
- **Diary entries snapshot their nutrient values.** Source data is revised and recipes are edited; a
  previous day's log must not change retroactively.
- **Missing nutrients are `NULL`, not zero.** Daily totals report which nutrients some entry did not
  provide, because a sum over gaps looks authoritative and is too low.
- **Targets and recipe totals are computed on read.** They are pure functions of their inputs, so a stored
  copy would go stale when an input changed.
- **"Today" is the user's local day.** The server computes `local_date` from the profile's time zone; the
  client never supplies it.
- **Provider calls are proxied and cached.** Open Food Facts allows 15 requests per minute per IP, and
  keys do not belong in a mobile bundle.
- **Search is curated first.** USDA and Open Food Facts rows appear only when nothing curated matches,
  so the default results are not dominated by laboratory-style names. Photo scanning uses a separate
  search function with full access to all sources.
- **Moderation is human.** A user-submitted food becomes visible to others only after an administrator
  approves it. A report never changes a food on its own; an upheld report against a USDA or Open Food
  Facts row withdraws it, because editing the numbers would leave the row claiming a provenance its
  values no longer have. Withdrawn foods remain readable in existing diary entries.
- **Tokens are held in `expo-secure-store`** (Keychain on iOS, Keystore on Android), not AsyncStorage.
- **Rate limits apply per IP and per account**, so a distributed attack cannot avoid the per-account limit
  and a shared address cannot lock out other users.

## Status and known limitations

| Area | State |
|---|---|
| Authentication, onboarding, targets, diary, recipes, catalogue, meals, photo scanning, progress, water | Implemented |
| Moderation console | Implemented; functional but visually plain |
| Food data | About 410 foods in the live database, of which 189 are Tunisian (INNTA). Ciqual (about 3,400 rows) is not imported |
| Backend tests | Passing; run time is several minutes |
| Mobile tests | None. The client is checked by the TypeScript compiler only |
| Email | Supabase's built-in mailer is rate limited and intended for development. Configure custom SMTP, then enable email confirmation, before real users |
| Languages | French and English. No Arabic interface |
| Gaps | Typo-tolerant search, offline support, dark mode, a fully translated plan screen |
