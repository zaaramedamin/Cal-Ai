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
  /** App canvas. Cool, modern slate background. */
  canvas: '#F8FAFC',
  /** Cards and floating surfaces. Crisp pure white. */
  surface: '#FFFFFF',
  /** Primary text. Deep obsidian navy. */
  ink: '#0F172A',

  /** Modern Indigo/Violet Action Color. */
  accent: '#6366F1',
  /** Rich Gradient Accent End */
  accentGradientEnd: '#4F46E5',
  /** Pressed and active state. */
  accentDeep: '#4338CA',

  /** Protein. Rich Salmon/Coral Red. */
  protein: '#EF4444',
  proteinGradientEnd: '#F87171',

  /** Carbohydrate. Vibrant Warm Amber. */
  carbs: '#F59E0B',
  carbsGradientEnd: '#FBBF24',

  /** Fat. Electric Sky Blue. */
  fat: '#3B82F6',
  fatGradientEnd: '#60A5FA',

  /** Water. Vivid Cyan/Teal. */
  water: '#06B6D4',
  waterGradientEnd: '#22D3EE',

  /** Streak flame accent. */
  flame: '#F97316',

  /** On track / Goal met green. */
  positive: '#10B981',
  /** Warning / Check this. */
  warning: '#F59E0B',
  /** Danger / Error. */
  danger: '#EF4444',
} as const;

const INK_RGB = '15, 23, 42';

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
  inkMuted: `rgba(${INK_RGB}, 0.60)`,
  /** Tertiary text and disabled icons. */
  inkFaint: `rgba(${INK_RGB}, 0.35)`,
  /** Hairline separators on white. */
  hairline: `rgba(${INK_RGB}, 0.08)`,
  /** Neutral pressed/selected wash and empty ring tracks. */
  wash: `rgba(${INK_RGB}, 0.05)`,

  /** Text and icons on `ink`, `accent` and the macro colours. */
  onDark: '#FFFFFF',

  // ---- Tinted surfaces --------------------------------------------------
  // Backgrounds for cards, chips and badges that belong to a category.
  accentTint: tint(palette.accent, 0.10),
  accentTintStrong: tint(palette.accent, 0.18),
  proteinTint: tint(palette.protein, 0.11),
  carbsTint: tint(palette.carbs, 0.13),
  fatTint: tint(palette.fat, 0.11),
  waterTint: tint(palette.water, 0.12),
  positiveTint: tint(palette.positive, 0.11),
  warningTint: tint(palette.warning, 0.13),
  dangerTint: tint(palette.danger, 0.09),
  flameTint: tint(palette.flame, 0.11),

  // Aliases kept so older screens keep compiling while they are restyled.
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
 * Modern shadow elevations with soft colored ambient glows.
 */
const shadow = (y: number, blur: number, opacity: number, elevation: number, shadowColor = '#0F172A'): ViewStyle =>
  Platform.select({
    ios: {
      shadowColor,
      shadowOffset: { width: 0, height: y },
      shadowOpacity: opacity,
      shadowRadius: blur,
    },
    default: { elevation },
  }) as ViewStyle;

export const elevation = {
  /** Cards resting on the canvas. */
  low: shadow(4, 14, 0.04, 2),
  /** Raised cards, selected chips, sheets. */
  mid: shadow(8, 22, 0.08, 6),
  /** Floating navigation bar, modal sheets. */
  glass: shadow(12, 32, 0.12, 10),
  /** Floating action buttons and modals. */
  high: shadow(10, 26, 0.14, 12),
  /** Glowing FAB action button. */
  accentGlow: shadow(8, 20, 0.35, 10, palette.accent),
} as const;

/** Back-compat: the old single shadow token, now the low elevation. */
export const cardShadow: ViewStyle = elevation.low;

export const duration = {
  instant: 120,
  quick: 220,
  gentle: 600,
} as const;

export const HIT_SLOP_MIN = 44;

export type SpaceToken = keyof typeof space;
export type RadiusToken = keyof typeof radius;
export type ColorToken = keyof typeof color;

