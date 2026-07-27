/**
 * Design tokens — CalDiet-style system.
 *
 * The look: a cool light-gray canvas, white cards with soft shadows, black as
 * the single action colour, and one accent per macro used for progress rings
 * and bars. Numbers are the heroes; chrome stays quiet.
 *
 * Every colour, space and radius in the app comes from here. No raw hex values
 * and no magic numbers in component styles — that rule is what keeps a redesign
 * like this one a single-file palette change instead of a fifty-file hunt.
 */

import { Platform, type ViewStyle } from 'react-native';

const palette = {
  /** App canvas. Cool light gray so white cards visibly lift off it. */
  canvas: '#F4F5F7',
  /** Cards and sheets. */
  surface: '#FFFFFF',
  /** Primary text and the action colour. Near-black, slightly warm. */
  ink: '#17181A',
  /** Protein ring and bar. Red-salmon. */
  protein: '#E8564B',
  /** Carbohydrate ring and bar. Amber. */
  carbs: '#EFA036',
  /** Fat ring and bar. Blue. */
  fat: '#4C86E8',
  /** The streak flame and calorie accents. */
  flame: '#F2762E',
} as const;

const INK_RGB = '23, 24, 26';

export const color = {
  ...palette,

  /** Secondary text: timestamps, units, helper copy. */
  inkMuted: `rgba(${INK_RGB}, 0.55)`,
  /** Tertiary text and disabled icons. */
  inkFaint: `rgba(${INK_RGB}, 0.32)`,
  /** Hairline separators on white. */
  hairline: `rgba(${INK_RGB}, 0.08)`,
  /** Pressed/selected wash and empty ring tracks on white cards. */
  wash: `rgba(${INK_RGB}, 0.06)`,

  /** Text and icons on `ink` (buttons) and on macro colours. */
  onDark: '#FFFFFF',

  /** Success/positive (weight trending toward goal). */
  positive: '#3BA55D',
  /** Errors and destructive actions. */
  danger: '#D64545',

  // Back-compat aliases used by the auth/onboarding screens' error callouts.
  clay: '#17181A',
  clayDeep: '#D64545',
  inkWash: `rgba(${INK_RGB}, 0.06)`,
  paper: '#F4F5F7',
} as const;

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

/**
 * Generous radii are half the look. Cards at 20, buttons and inputs at 14,
 * chips at pill.
 */
export const radius = {
  sm: 10,
  md: 14,
  lg: 20,
  xl: 28,
  pill: 999,
} as const;

/**
 * The soft card shadow. Defined once because iOS and Android disagree about
 * everything here: iOS wants shadow* properties, Android wants elevation, and
 * mixing them per-screen produces cards that match on one platform only.
 */
export const cardShadow: ViewStyle = Platform.select({
  ios: {
    shadowColor: '#101215',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 14,
  },
  default: { elevation: 2 },
});

/** Minimum touch target. Below this, taps start missing. */
export const HIT_SLOP_MIN = 44;

export type SpaceToken = keyof typeof space;
export type RadiusToken = keyof typeof radius;
export type ColorToken = keyof typeof color;
