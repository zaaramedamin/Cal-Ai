/**
 * Photography used across the app.
 *
 * **Why this indirection instead of `require()` at each call site.**
 *
 * Metro resolves `require('../../assets/photos/x.jpg')` at build time, so a
 * missing file is a *bundling failure* — the whole app refuses to start, not
 * just the screen with the gap. Routing every image through one module means
 * there is one list to keep in step with the folder, one place to see what the
 * app expects, and one place to change when the art direction does.
 *
 * `photo()` returns `null` when a slot is unfilled, and every screen that uses
 * imagery is built to look finished without it. That is deliberate: the app has
 * to be presentable on a fresh clone before anyone has sourced photography, and
 * a half-designed screen waiting on assets is a screen nobody can review.
 *
 * ---
 *
 * **To add the photos**, save them into `mobile/assets/photos/` with these exact
 * names, then uncomment the matching line below:
 *
 *   auth-hero.jpg      a bright kitchen scene — chopping, prepping, weighing
 *   onboarding-1.jpg   a plated meal, shot from above
 *   onboarding-2.jpg   someone eating well, warm and human
 *   onboarding-3.jpg   a spread of prepped meals
 *   empty-diary.jpg    a single simple plate, calm and uncluttered
 *   empty-meals.jpg    several dishes together — what a saved meal could be
 *   onboarding-done.jpg  the payoff shot for the last onboarding step
 *   body-figure.png    a standing person, full length, on a transparent
 *                      background — the dashboard figure
 *
 * Landscape crops around 1600×1000 for the hero, square for the rest. Keep each
 * under ~300 KB — they ship inside the app, and the bundle is already 7.5 MB.
 *
 * ---
 *
 * **`bodyFigure` comes with a trade-off worth understanding before using it.**
 *
 * The dashboard figure is currently drawn as SVG *from the user's own height and
 * weight*, and it morphs as those change. A photograph cannot do that: one image
 * is one body, and it will be somebody else's. Dropping a file in here replaces
 * a figure that means something about the person looking at it with a picture
 * that does not.
 *
 * If a photograph is still wanted, the honest version is one per BMI band so it
 * still responds to their numbers — at which point this becomes four or eight
 * files rather than one. `BodyAvatar` falls back to the drawn figure whenever
 * this slot is empty, so the app is complete either way.
 */

import type { ImageSourcePropType } from 'react-native';

export type PhotoSlot =
  /** The dashboard figure. Empty by default — see the note above. */
  | 'bodyFigure'
  | 'authHero'
  | 'onboarding1'
  | 'onboarding2'
  | 'onboarding3'
  | 'emptyDiary'
  | 'emptyMeals'
  | 'onboardingDone';

/**
 * Filled slots. Each entry stays commented until its file exists, because an
 * uncommented `require` for a missing file breaks the build rather than the
 * screen.
 */
const PHOTOS: Partial<Record<PhotoSlot, ImageSourcePropType>> = {
  // Commented until the file exists — an uncommented `require` for a missing
  // file fails the *bundle*, not the screen. See the note on `bodyFigure` in
  // the header above before filling this one in.
  // bodyFigure: require('../../assets/photos/body-figure.png'),
  authHero: require('../../assets/photos/auth-hero.jpg'),
  onboarding1: require('../../assets/photos/onboarding-1.jpg'),
  onboarding2: require('../../assets/photos/onboarding-2.jpg'),
  onboarding3: require('../../assets/photos/onboarding-3.jpg'),
  emptyDiary: require('../../assets/photos/empty-diary.jpg'),
  emptyMeals: require('../../assets/photos/empty-meals.jpg'),
  onboardingDone: require('../../assets/photos/onboarding-done.jpg'),
};

export function photo(slot: PhotoSlot): ImageSourcePropType | null {
  return PHOTOS[slot] ?? null;
}

export function hasPhoto(slot: PhotoSlot): boolean {
  return PHOTOS[slot] !== undefined;
}
