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

  /**
   * Indigo, the action colour. `#4F46E5` rather than the lighter `#6366F1` it
   * replaced: white on that one measured 4.47:1, just under the 4.5:1 WCAG AA
   * floor for text the size of a button label, and the same hue as link text on
   * white failed the same way. This one is 6.3:1 either way round.
   */
  accent: '#4F46E5',
  /** Rich Gradient Accent End */
  accentGradientEnd: '#4338CA',
  /** Pressed and active state. */
  accentDeep: '#3730A3',

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
  /**
   * Danger / Error. A deeper red than protein's on purpose: they were the same
   * `#EF4444`, so an error message and a protein figure read as one thing, and
   * white on it (the danger button) was 3.8:1.
   */
  danger: '#DC2626',

  // ---- Text-safe hues -----------------------------------------------------
  // The hues above are for fills, rings, bars and dots. As *text* most of them
  // are unreadable — amber on white is 2.1:1, cyan 2.4:1, green 2.5:1 — so any
  // coloured word or number uses the matching shade below instead. Each is
  // 4.5:1 or better on white, on the canvas, and on its own tint.
  proteinText: '#B91C1C',
  carbsText: '#B45309',
  fatText: '#1D4ED8',
  waterText: '#0E7490',
  flameText: '#C2410C',
  positiveText: '#047857',
  warningText: '#B45309',
  dangerText: '#B91C1C',
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

  /**
   * Secondary text: timestamps, units, helper copy. 0.64 rather than 0.60 so it
   * still clears 4.5:1 on the grey `wash` behind chips and legends, not only on
   * white.
   */
  inkMuted: `rgba(${INK_RGB}, 0.64)`,
  /**
   * Disabled icons and decorative ticks only — 2.2:1, so **never for text** a
   * person needs to read. Inactive tab labels were drawn in this and could not
   * be read at arm's length.
   */
  inkFaint: `rgba(${INK_RGB}, 0.35)`,
  /** Text and icons on `accent` that are secondary to a label beside them. */
  onDarkMuted: 'rgba(255, 255, 255, 0.85)',
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

  /** Dimmed backdrop behind a sheet or menu. */
  scrim: `rgba(${INK_RGB}, 0.45)`,

  // The aliases that lived here — `clay`, `clayDeep`, `inkWash`, `paper` —
  // were kept "while older screens are restyled". That restyle is finished and
  // they are gone: `clayDeep` in particular read as a pressed accent and
  // painted things red.
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

