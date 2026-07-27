/**
 * Type system.
 *
 * Two families, each with one job:
 *
 * **Fraunces** — hero numerals and headers. A serif with genuine character:
 * high contrast, a slight wonkiness in the letterforms, and old-style warmth
 * that suits food. A treadmill app would look wrong in it, which is exactly why
 * it makes CalAi recognisable. Calorie counts are the hero content of this app,
 * so the numerals are the thing people should remember.
 *
 * **Inter** — every piece of UI and body text. Designed for screens at small
 * sizes, with tall x-height and unambiguous 1/l/I. It gets out of the way, which
 * is the whole point of a body face.
 *
 * The serif is *hero-only*. A dense diary list rendered in Fraunces at 13px would
 * trade real legibility for decoration — the pairing works because each face is
 * used where it is actually better, not to be interesting.
 *
 * Note: @expo-google-fonts ships static instances of Fraunces, not the variable
 * font, so its optical-size and WONK axes are not adjustable at runtime. Shipping
 * the variable TTF would be needed for that, and React Native has no portable
 * `font-variation-settings` equivalent. The static SemiBold/Bold cuts are what we
 * use, and they carry the character we want.
 */

// Deep subpath imports, deliberately — NOT `from '@expo-google-fonts/inter'`.
//
// The package root re-exports every weight, and each of those re-exports
// `require()`s its own .ttf. Metro cannot tree-shake that away, so importing
// from the root bundles all ~18 weights of both families: measured at 8 MB of
// dead font data in the Android bundle. Importing the specific weight's module
// pulls exactly one file each.
import { Fraunces_600SemiBold } from '@expo-google-fonts/fraunces/600SemiBold';
import { Fraunces_700Bold } from '@expo-google-fonts/fraunces/700Bold';
import { Inter_400Regular } from '@expo-google-fonts/inter/400Regular';
import { Inter_500Medium } from '@expo-google-fonts/inter/500Medium';
import { Inter_600SemiBold } from '@expo-google-fonts/inter/600SemiBold';
import type { TextStyle } from 'react-native';

import { color } from './tokens';

/** Passed to `useFonts`. Keys here are the names referenced in `fontFamily`. */
export const fontAssets = {
  Fraunces_600SemiBold,
  Fraunces_700Bold,
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
} as const;

export const fontFamily = {
  displaySemiBold: 'Fraunces_600SemiBold',
  displayBold: 'Fraunces_700Bold',
  bodyRegular: 'Inter_400Regular',
  bodyMedium: 'Inter_500Medium',
  bodySemiBold: 'Inter_600SemiBold',
} as const;

/**
 * `tabular-nums` locks every digit to the same advance width, so a counter
 * ticking 998 -> 999 -> 1000 does not shuffle the layout sideways. Support is
 * solid on iOS and good on recent Android; where it is ignored the text simply
 * renders proportionally, so this degrades rather than breaks.
 */
const TABULAR: Pick<TextStyle, 'fontVariant'> = { fontVariant: ['tabular-nums'] };

export const text = {
  /** The daily calorie total. One per screen, at most. */
  hero: {
    fontFamily: fontFamily.displaySemiBold,
    fontSize: 52,
    lineHeight: 56,
    letterSpacing: -1.2,
    color: color.ink,
    ...TABULAR,
  },
  /** Screen titles. */
  title: {
    fontFamily: fontFamily.displaySemiBold,
    fontSize: 28,
    lineHeight: 34,
    letterSpacing: -0.4,
    color: color.ink,
  },
  /** Section headers and secondary hero numbers (per-macro grams). */
  heading: {
    fontFamily: fontFamily.displaySemiBold,
    fontSize: 20,
    lineHeight: 26,
    letterSpacing: -0.2,
    color: color.ink,
    ...TABULAR,
  },
  /** Default body copy. */
  body: {
    fontFamily: fontFamily.bodyRegular,
    fontSize: 15,
    lineHeight: 22,
    color: color.ink,
  },
  /** Body copy that is supporting rather than primary. */
  bodyMuted: {
    fontFamily: fontFamily.bodyRegular,
    fontSize: 15,
    lineHeight: 22,
    color: color.inkMuted,
  },
  /** Buttons, list-row primary text, form labels. */
  label: {
    fontFamily: fontFamily.bodyMedium,
    fontSize: 14,
    lineHeight: 20,
    color: color.ink,
  },
  /**
   * Small uppercase eyebrow text. The wide tracking is doing the work here —
   * uppercase at 11px without it is a solid illegible block.
   */
  overline: {
    fontFamily: fontFamily.bodySemiBold,
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 1.1,
    textTransform: 'uppercase',
    color: color.inkFaint,
  },
  /** Numbers inside dense rows — Inter, not Fraunces, for legibility at size. */
  numeric: {
    fontFamily: fontFamily.bodyMedium,
    fontSize: 14,
    lineHeight: 20,
    color: color.ink,
    ...TABULAR,
  },
} satisfies Record<string, TextStyle>;

export type TextToken = keyof typeof text;
