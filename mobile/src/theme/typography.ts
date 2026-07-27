/**
 * Type system — Inter only.
 *
 * The CalDiet look is a single clean grotesque at several weights: extra-bold
 * for hero numerals, semibold for titles and values, regular for supporting
 * copy. One family keeps the UI quiet so the numbers carry the screen.
 *
 * Deep subpath imports, deliberately — NOT `from '@expo-google-fonts/inter'`.
 * The package root re-exports every weight and each re-export `require()`s its
 * own .ttf; Metro cannot tree-shake that, so importing the root bundles all ~18
 * weights (measured: 8 MB of dead font data). Subpath imports pull exactly the
 * five files used.
 */

import { Inter_400Regular } from '@expo-google-fonts/inter/400Regular';
import { Inter_500Medium } from '@expo-google-fonts/inter/500Medium';
import { Inter_600SemiBold } from '@expo-google-fonts/inter/600SemiBold';
import { Inter_700Bold } from '@expo-google-fonts/inter/700Bold';
import { Inter_800ExtraBold } from '@expo-google-fonts/inter/800ExtraBold';
import type { TextStyle } from 'react-native';

import { color } from './tokens';

/** Passed to `useFonts`. Keys here are the names referenced in `fontFamily`. */
export const fontAssets = {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  Inter_800ExtraBold,
} as const;

export const fontFamily = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semiBold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
  extraBold: 'Inter_800ExtraBold',
} as const;

/**
 * `tabular-nums` locks every digit to the same advance width, so a counter
 * ticking 998 -> 999 -> 1000 does not shuffle the layout sideways.
 */
const TABULAR: Pick<TextStyle, 'fontVariant'> = { fontVariant: ['tabular-nums'] };

export const text = {
  /** The calories-left number in the dashboard ring. One per screen, at most. */
  hero: {
    fontFamily: fontFamily.extraBold,
    fontSize: 44,
    lineHeight: 50,
    letterSpacing: -1,
    color: color.ink,
    ...TABULAR,
  },
  /** Screen titles. */
  title: {
    fontFamily: fontFamily.bold,
    fontSize: 26,
    lineHeight: 32,
    letterSpacing: -0.4,
    color: color.ink,
  },
  /** Card headings and mid-size numbers (macro card values). */
  heading: {
    fontFamily: fontFamily.bold,
    fontSize: 19,
    lineHeight: 25,
    letterSpacing: -0.2,
    color: color.ink,
    ...TABULAR,
  },
  /** Default body copy. */
  body: {
    fontFamily: fontFamily.regular,
    fontSize: 15,
    lineHeight: 22,
    color: color.ink,
  },
  /** Supporting copy. */
  bodyMuted: {
    fontFamily: fontFamily.regular,
    fontSize: 15,
    lineHeight: 22,
    color: color.inkMuted,
  },
  /** Buttons, list-row primary text, form labels. */
  label: {
    fontFamily: fontFamily.semiBold,
    fontSize: 14,
    lineHeight: 20,
    color: color.ink,
  },
  /** Small uppercase eyebrow text. */
  overline: {
    fontFamily: fontFamily.semiBold,
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    color: color.inkMuted,
  },
  /** Numbers inside dense rows. */
  numeric: {
    fontFamily: fontFamily.semiBold,
    fontSize: 14,
    lineHeight: 20,
    color: color.ink,
    ...TABULAR,
  },
} satisfies Record<string, TextStyle>;

export type TextToken = keyof typeof text;
