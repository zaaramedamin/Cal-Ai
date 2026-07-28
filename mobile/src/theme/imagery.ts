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
 *
 * Landscape crops around 1600×1000 for the hero, square for the rest. Keep each
 * under ~300 KB — they ship inside the app, and the bundle is already 7.5 MB.
 */

import type { ImageSourcePropType } from 'react-native';

export type PhotoSlot =
  | 'authHero'
  | 'onboarding1'
  | 'onboarding2'
  | 'onboarding3'
  | 'emptyDiary';

/**
 * Filled slots. Each entry stays commented until its file exists, because an
 * uncommented `require` for a missing file breaks the build rather than the
 * screen.
 */
const PHOTOS: Partial<Record<PhotoSlot, ImageSourcePropType>> = {
  // authHero: require('../../assets/photos/auth-hero.jpg'),
  // onboarding1: require('../../assets/photos/onboarding-1.jpg'),
  // onboarding2: require('../../assets/photos/onboarding-2.jpg'),
  // onboarding3: require('../../assets/photos/onboarding-3.jpg'),
  // emptyDiary: require('../../assets/photos/empty-diary.jpg'),
};

export function photo(slot: PhotoSlot): ImageSourcePropType | null {
  return PHOTOS[slot] ?? null;
}

export function hasPhoto(slot: PhotoSlot): boolean {
  return PHOTOS[slot] !== undefined;
}
