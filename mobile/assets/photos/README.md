# Photography

Drop image files here, then uncomment the matching line in
`src/theme/imagery.ts`. Nothing else needs changing — every screen that uses a
photo already renders a designed fallback when the slot is empty, so the app
looks finished before any of these exist.

| File | Where it appears | Shape |
|---|---|---|
| `auth-hero.jpg` | Behind the wordmark on sign in / sign up | landscape, ~1600×1000 |
| `onboarding-1.jpg` | Onboarding carousel | square, ~1024 |
| `onboarding-2.jpg` | Onboarding carousel | square, ~1024 |
| `onboarding-3.jpg` | Onboarding carousel | square, ~1024 |
| `onboarding-done.jpg` | The final onboarding step | square, ~1024 |
| `empty-diary.jpg` | The "nothing logged yet" card | landscape, ~1200×600 |
| `empty-meals.jpg` | The "no meals yet" screen | landscape, ~1200×600 |

Keep each under roughly 300 KB. These ship inside the app rather than loading
from a server — bundling them means they work offline and reveal nothing about
what the user is browsing, but it also means every kilobyte is one the user
downloads once and carries forever. The bundle is already 7.5 MB.

`.jpg` for photographs, not `.png`: a photograph as PNG is typically five to ten
times larger for no visible gain, because PNG is lossless and built for flat
colour and sharp edges.

## What these are not

**Not the catalogue photos.** Those are one shot per food — `chicken-breast.jpg`,
`egg.jpg`, `milk.jpg` — and they do not live in the app bundle at all. They are
imported into the `food_photos` table with
`python -m app.cli import-photos <folder>` and served from the API, because there
are 35 of them and they change independently of app releases.

The images here are the opposite case: a handful, changing only when the design
does, wanted instantly and offline. Different lifetimes, different homes.

## Cropping

The hero is the one to be careful with. It sits behind white text under a
gradient scrim, so choose a frame whose *lower half* is uncluttered — the calorie
card overlaps the bottom edge, and detail there fights with it. A busy top is
fine; the scrim is lightest where nothing is drawn.
