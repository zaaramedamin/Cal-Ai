/**
 * Design tokens.
 *
 * The look: a soft blue-grey canvas, white cards, **indigo as the action
 * colour**, and each macro owning a tinted surface of its own rather than a
 * single coloured dot.
 *
 * **Why indigo instead of black.** Black is a safe action colour and a mute
 * one: when the button, the selected chip, the ring and the body text are all
 * the same near-black, nothing on screen claims to be the thing you came to do.
 * One saturated hue reserved strictly for "you can act here" makes the whole
 * interface easier to read at a glance, and leaves black free to do what it is
 * good at — text.
 *
 * **Why every accent ships with a tint.** A 12%-opacity wash of the same hue
 * turns a card into a category without adding a border or an icon. It is the
 * cheapest hierarchy there is, and it is why the macro tiles can be read
 * peripherally — you learn "amber is carbs" once and never read the label again.
 *
 * Every colour, space, radius, shadow and duration in the app comes from here.
 * No raw hex and no magic numbers in component styles — that rule is what keeps
 * a restyle a single-file change rather than a fifty-file hunt.
 */

import { Platform, type ViewStyle } from 'react-native';

const palette = {
  /** App canvas. Cool and very slightly blue, so white cards lift off it. */
  canvas: '#F5F6FA',
  /** Cards and sheets. */
  surface: '#FFFFFF',
  /** Primary text. Near-black with a blue cast, to sit with the accent. */
  ink: '#14161D',

  /** The action colour. Buttons, focus rings, selection, the calorie ring. */
  accent: '#4F46E5',
  /** Pressed and active states. */
  accentDeep: '#4338CA',

  /** Protein. Salmon-red. */
  protein: '#F0544F',
  /** Carbohydrate. Amber. */
  carbs: '#F2A93B',
  /** Fat. Blue. */
  fat: '#4C86E8',

  /** Streak flame and calorie accents. */
  flame: '#F97316',

  /** On track, goal met, weight trending the right way. */
  positive: '#16A34A',
  /** Over target, low confidence, "check this" — never an error. */
  warning: '#F59E0B',
  /** Errors and destructive actions. */
  danger: '#DC2626',
} as const;

const INK_RGB = '20, 22, 29';

/** A translucent wash of a hue, for tinted surfaces on white. */
const tint = (hex: string, alpha: number): string => {
  const r = Number.parseInt(hex.slice(1, 3), 16);
  const g = Number.parseInt(hex.slice(3, 5), 16);
  const b = Number.parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

export const color = {
  ...palette,

  /** Secondary text: timestamps, units, helper copy. */
  inkMuted: `rgba(${INK_RGB}, 0.56)`,
  /** Tertiary text and disabled icons. */
  inkFaint: `rgba(${INK_RGB}, 0.32)`,
  /** Hairline separators on white. */
  hairline: `rgba(${INK_RGB}, 0.07)`,
  /** Neutral pressed/selected wash and empty ring tracks. */
  wash: `rgba(${INK_RGB}, 0.05)`,

  /** Text and icons on `ink`, `accent` and the macro colours. */
  onDark: '#FFFFFF',

  // ---- Tinted surfaces --------------------------------------------------
  // Backgrounds for cards, chips and badges that belong to a category. Light
  // enough to carry black text at full contrast.
  accentTint: tint(palette.accent, 0.1),
  accentTintStrong: tint(palette.accent, 0.16),
  proteinTint: tint(palette.protein, 0.11),
  carbsTint: tint(palette.carbs, 0.13),
  fatTint: tint(palette.fat, 0.11),
  positiveTint: tint(palette.positive, 0.11),
  warningTint: tint(palette.warning, 0.13),
  dangerTint: tint(palette.danger, 0.09),
  flameTint: tint(palette.flame, 0.11),

  // Aliases kept so older screens keep compiling while they are restyled.
  // They now resolve to the new palette rather than to black, so those screens
  // pick up the accent without being touched.
  clay: palette.accent,
  clayDeep: palette.danger,
  inkWash: `rgba(${INK_RGB}, 0.05)`,
  paper: palette.canvas,
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

/** Generous radii are half the look. Cards 20, controls 14, chips pill. */
export const radius = {
  sm: 10,
  md: 14,
  lg: 20,
  xl: 28,
  pill: 999,
} as const;

/**
 * Three elevations rather than one.
 *
 * A single shadow makes every surface equally important. Cards sit low, things
 * that float over content (the FAB, sheets, toasts) sit high, and the gap
 * between them is what tells you which layer you are looking at.
 *
 * Defined once because iOS and Android disagree about all of it — iOS wants
 * shadow*, Android wants elevation — and mixing them per-screen produces cards
 * that match on one platform only.
 */
const shadow = (y: number, blur: number, opacity: number, elevation: number): ViewStyle =>
  Platform.select({
    ios: {
      shadowColor: '#0B1020',
      shadowOffset: { width: 0, height: y },
      shadowOpacity: opacity,
      shadowRadius: blur,
    },
    default: { elevation },
  }) as ViewStyle;

export const elevation = {
  /** Cards resting on the canvas. */
  low: shadow(3, 12, 0.05, 2),
  /** Raised cards, selected chips, sheets. */
  mid: shadow(6, 18, 0.09, 6),
  /** The FAB, toasts, anything above the content. */
  high: shadow(10, 26, 0.14, 12),
} as const;

/** Back-compat: the old single shadow token, now the low elevation. */
export const cardShadow: ViewStyle = elevation.low;

/**
 * Animation timings.
 *
 * Short by deliberate choice. An interface animation is feedback, not
 * entertainment: past roughly 300ms it stops reading as responsive and starts
 * reading as slow, and the user notices it on the fiftieth log of the week even
 * though it delighted them on the first.
 */
export const duration = {
  /** Press feedback, chip selection. */
  instant: 120,
  /** Most transitions: fades, slides, colour changes. */
  quick: 220,
  /** Rings and bars filling, numbers counting. */
  gentle: 600,
} as const;

/** Minimum touch target. Below this, taps start missing. */
export const HIT_SLOP_MIN = 44;

export type SpaceToken = keyof typeof space;
export type RadiusToken = keyof typeof radius;
export type ColorToken = keyof typeof color;
