# CalAi

A calorie and macronutrient tracking app. Set your body stats and a goal, get evidence-based daily
calorie and macro targets, then log what you eat against them.

**Status: phases 0–5 shipped, plus AI photo scanning.** Auth, onboarding and targets, USDA search,
the diary, recipes, meal photo scanning, quick-add and meal suggestions all work end to end.
Remaining phases are listed at the bottom.

---

## Ground rule: nutrition data is never invented

No nutrition value in this app is estimated, guessed, or hardcoded. Every food comes from
[USDA FoodData Central](https://fdc.nal.usda.gov/) or [Open Food Facts](https://world.openfoodfacts.org/),
and every stored row keeps its `source` and `source_id` so any number on screen can be traced back
to its origin. Where a source genuinely does not report a nutrient, the app shows `—`, never `0`.

**This rule is why the AI photo scanner is built the way it is.** Asking a vision model "how many
calories is this?" would break it on the first request. So the model is never asked. It answers only
*which foods are on the plate* and *roughly how many grams of each* — its output schema has no field
for a calorie — and those names are then matched against the USDA-backed database, which supplies
every number. The user confirms the portions before anything is logged. The AI proposes, USDA
prices, the user decides.

---

## Stack

| Layer | Choice |
|---|---|
| Mobile | Expo SDK 54 (React Native 0.81, React 19.1), TypeScript strict, expo-router |
| Backend | FastAPI, Python 3.13, SQLAlchemy 2.0 async, Pydantic v2 |
| Database | PostgreSQL 16 via Docker Compose |
| Migrations | Alembic, from the very first table |

---

## Setup from zero

### 1. Prerequisites

On a machine with nothing installed (Windows):

```powershell
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.13
winget install Docker.DockerDesktop
```

Docker Desktop needs virtualization enabled. If `wsl --status` says WSL is not installed:

```powershell
wsl --install --no-distribution     # elevated; requires a reboot
```

**Then turn off the Python Store aliases**: Settings → Apps → Advanced app settings → App execution
aliases → toggle off `python.exe` and `python3.exe`. Windows ships a 0-byte stub at those names that
shadows the real interpreter, so `python` silently opens the Microsoft Store instead of running
anything. This costs everyone an hour exactly once.

Verify in a **new** terminal: `node -v`, `python --version`, `docker --version`.

### 2. Environment file

```powershell
Copy-Item .env.example .env
```

Then generate a real secret and paste it in as `SECRET_KEY`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

`.env` is gitignored. `.env.example` is committed and documents every variable — it must never
contain a real secret.

**Optional — AI meal photo scanning.** Leave `GEMINI_API_KEY` blank and everything else works; the
scan screen simply reports that the feature is switched off. To enable it, get a free key from
[Google AI Studio](https://aistudio.google.com/apikey) (no credit card, roughly 250 scans a day) and
paste it in:

```
GEMINI_API_KEY=AIza...
```

### 3. Database

```powershell
docker compose up -d
docker compose ps          # wait for "healthy"
```

### 4. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Check it: <http://localhost:8000/api/v1/health> should return
`{"status":"ok","version":"0.1.0","db":"ok"}`, and <http://localhost:8000/docs> has the interactive
API browser.

### 5. Mobile

In a second terminal:

```powershell
cd mobile
npm install
npx expo start
```

Install **Expo Go** on your phone, make sure it is on the same Wi-Fi as your computer, and scan the
QR code.

---

### If PowerShell refuses to run scripts

Windows blocks script execution by default, so `Activate.ps1` and `npx` both fail with
*"running scripts is disabled on this system"*. Fix it once — no admin rights needed, since
`-Scope CurrentUser` only touches your own account:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

`RemoteSigned` still blocks unsigned scripts downloaded from the internet; it only trusts local
ones. It is the usual setting on a Windows development machine.

If you would rather change nothing, both tools have a form that sidesteps PowerShell entirely —
`npx.cmd expo start` runs as a batch file, and calling the interpreter directly does exactly what
activation does, since activating a virtualenv only prepends `.venv\Scripts` to `PATH`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## The three things that will break on Windows

All of these produce a "cannot reach the backend" error, or an app that never finishes loading,
with no obvious cause. The app's error screen names the first two, and here they are in full.

### Expo picks the wrong IP when WSL or Hyper-V is installed

`ipconfig` on this machine lists three IPv4 addresses:

```
192.168.1.124   Wi-Fi          <- the only one the phone can reach
172.21.80.1     vEthernet (WSL)
172.17.96.1     vEthernet (Default Switch)
```

Expo picks one of them to advertise to the phone, and it does not always pick the Wi-Fi one. When
it picks a virtual adapter the failure is total and confusing: the phone cannot fetch the JS
bundle, **and** it cannot reach the API either — `resolveApiBaseUrl()` in `mobile/src/api/client.ts`
derives the backend host from the same address Expo served the bundle from. One wrong guess breaks
both, and the app simply never starts.

Pin it explicitly:

```powershell
$env:REACT_NATIVE_PACKAGER_HOSTNAME = "192.168.1.124"   # your Wi-Fi IP, from ipconfig
npx expo start -c
```

Check it worked — the printed URL and the QR code should both show the Wi-Fi address, not a
`172.x` one.

### uvicorn must bind `0.0.0.0`

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000   # correct
uvicorn app.main:app --reload                              # phone can NEVER reach this
```

The default binds `127.0.0.1`, which accepts connections originating from that machine only. Your
phone's request is refused before it reaches any application code.

Related: `localhost` typed on a phone means *the phone*, which is running no server. The app never
hardcodes an address — it reads the host Expo served the bundle from and targets port 8000 on the
same machine, so it keeps working when your router hands out a different IP.

### Use `127.0.0.1`, never `localhost`, in `DATABASE_URL`

`localhost` resolves to the IPv6 address `::1` before IPv4, but Docker Compose
publishes Postgres on IPv4 only. Every new connection therefore waits for the IPv6
attempt to fail before retrying — and nothing reports an error, so it just looks like
a slow database.

Measured on this project:

| Host | Time per connection |
|---|---|
| `localhost` | 2123 ms |
| `127.0.0.1` | 84 ms |

It took the backend test suite from **4m 48s to 21s**. Connection pooling hides it in
normal development, which is exactly why it survives unnoticed until something opens
connections in a loop.

### Windows Firewall blocks inbound 8000

Run once, in an **elevated** PowerShell:

```powershell
New-NetFirewallRule -DisplayName "CalAi backend (8000)" -Direction Inbound `
  -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
```

`-Profile Private` is deliberate: the port opens on your home network, not on public Wi-Fi.

---

## Layout

```
calai/
├─ docker-compose.yml       Postgres 16, named volume, healthcheck
├─ .env.example             every variable, documented, no real values
├─ backend/
│  ├─ app/
│  │  ├─ main.py            app factory, CORS, router mounting
│  │  ├─ core/config.py     the only place environment variables are read
│  │  ├─ db/                async engine, session-per-request, ORM base
│  │  ├─ api/v1/            versioned routes
│  │  └─ schemas/           Pydantic request/response models
│  └─ alembic/versions/     migrations — the schema's only source of truth
└─ mobile/
   └─ src/
      ├─ app/               expo-router file-based routes
      ├─ api/               HTTP client, base URL resolution, error taxonomy
      ├─ theme/             design tokens and type scale
      └─ components/        UI primitives
```

`src/app/` holds routes only; real logic lives beside it in `src/`. That keeps the router tree
readable as a sitemap rather than a dumping ground.

---

## Verifying Phase 0

```powershell
cd backend;  ruff check .              # lint clean
cd ..\mobile; npx tsc --noEmit         # strict-mode typecheck clean
```

Then the real test — the negative case matters as much as the positive one:

1. With everything running, the phone shows the round-trip time, `Backend v0.1.0`, and
   `Database Connected`.
2. Run `docker compose stop` and tap **Check again**. The screen must show *Postgres isn't
   reachable* with the command to fix it — the API is still up, so this is a partial failure and it
   is reported as one, not as a generic error.
3. Stop uvicorn and tap **Check again**. The screen must show *Cannot reach the backend* with the
   numbered checklist. Not a crash, and not a spinner that never ends.

If step 2 and 3 look identical, the error handling is not actually doing its job.

---

## Notable decisions

- **FastAPI over Express + TypeScript.** Pydantic v2 gives runtime validation and an OpenAPI schema
  from one declaration, and the nutrition maths wants Python's testing story. The real cost is
  losing one language across the stack — recovered by generating the mobile app's TypeScript client
  from the backend's OpenAPI schema, so a changed response shape becomes a compile error.
- **The backend proxies USDA and Open Food Facts; the app never calls them.** Open Food Facts allows
  15 requests/minute per IP — a handful of users typing in a search box would exhaust that and earn
  an IP ban. Caching in our own Postgres turns thousands of searches into a few upstream calls, and
  keeps the API key out of a mobile bundle, where nothing is secret.
- **The photo scanner splits identification from nutrition.** Gemini gets the photo and returns food
  names and gram estimates under a response schema with no nutrition field in it; the calories come
  from the USDA cache afterwards. The failure mode this buys is a survivable one — a hallucinating
  model names the wrong food, which the user sees on the review screen and corrects, instead of
  silently inventing a number that looks as authoritative as a real one. Photos are held in memory
  for the request and never stored.
- **The diary snapshots nutrient values at log time** rather than recalculating from the food row.
  USDA revises values and users edit recipes; last Tuesday's lunch must not change retroactively.
  Think invoice line item, not live price lookup.
- **A missing nutrient is `NULL`, never `0`, all the way to the screen.** If USDA doesn't report
  fibre, the app shows `—`. Day totals flag which nutrients any entry failed to report, because a
  total summed over holes looks authoritative and is quietly too low.
- **Targets and recipe nutrition are computed on read, never stored.** Both are pure functions of
  their inputs, so a stored copy goes stale the moment an input changes — and a stale calorie
  target is worse than none.
- **"Today" is the user's local day, never UTC.** `diary_entries.local_date` is computed server-side
  from the profile's IANA timezone. The client never dictates the date.
- **Passwords use argon2id; refresh tokens use SHA-256.** Different hashes for different inputs.
  A password is low-entropy and reused across sites, so it needs a deliberately slow, memory-hard
  hash. A refresh token is 256 bits we generated ourselves — nobody guesses it, so a slow hash
  would only add latency to every refresh.
- **Refresh tokens are opaque, not JWTs.** A JWT validates itself, which is exactly wrong here:
  every refresh must hit the database so revocation takes effect immediately. That is what makes
  logout mean something.
- **Rotation with theft detection, but only where theft is actually implied.** Replaying a *spent*
  token means two parties hold it, so every session is revoked. Replaying a *logged-out* token is
  almost always a stale client, and treating that as theft would make signing out on one device
  silently sign you out everywhere.
- **Tokens live in `expo-secure-store`, never AsyncStorage.** AsyncStorage is a plaintext file;
  SecureStore uses the iOS Keychain and Android's hardware-backed Keystore, so the OS holds the
  encryption key and the app never sees it.
- **Login is rate limited per IP *and* per account.** Per-IP alone is weak against a botnet, where
  every request comes from a different address and no per-IP budget is ever reached. A successful
  login clears the account's counter, so limits punish failure rather than use.
- **A completed password reset revokes every session.** People reset because they forgot — or
  because they think they were compromised. An attacker holds a refresh token, not the password,
  so changing the password alone would not touch them.

### Known limitation: rate limit counters are per-process

They live in the memory of one Python process. Two uvicorn workers keep separate tallies, so the
effective limit doubles, and a restart resets them. That is acceptable for a single-process
deployment and is genuinely weak at scale — the fix is Redis, and it is deliberately isolated to
`backend/app/core/rate_limit.py` so the swap touches one file.

### Known limitation: no email provider

`backend/app/services/email.py` logs the reset link instead of sending it, and in development the
token is echoed in the API response so the flow is testable end to end. The seam is real, so
adding a provider in Phase 7 changes that one module.

---

## Roadmap

| Phase | Delivers | Status |
|---|---|---|
| 0 | Monorepo, Postgres, health endpoint, Expo app proving the pipe | ✅ |
| 1 | Auth: register/login/refresh/logout, argon2id, JWT, secure token storage | ✅ |
| 2 | Onboarding, BMR/TDEE/macro targets with full unit tests, results screen | ✅ |
| 3 | USDA integration, normalization, caching, search | ✅ |
| 4 | Diary: log to meal slots, daily summary, macro bar | ✅ |
| 5 | Custom recipes with live nutrition totals | ✅ |
| — | AI meal photo scanning (Gemini identifies foods and portions; USDA prices them) | ✅ |
| 6 | Weight trends, weekly averages, streaks, empty/loading/error states throughout | |
| 7 | Deployment, builds, screenshots | |
