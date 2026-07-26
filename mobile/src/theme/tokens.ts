/**
 * Design tokens.
 *
 * Every colour, space and radius in the app comes from here. The rule is
 * absolute: no raw hex values and no magic numbers in component styles. That is
 * what makes a change to the system a one-line edit rather than a search across
 * fifty files, and it is why the app will look like one product instead of
 * fifty screens that were each styled on their own.
 */

/**
 * The six brand colours.
 *
 * The palette deliberately rejects the fitness-app default of neon green on
 * black. CalAi is about food, so the base is warm — `paper` and `ink` read like
 * printed stock rather than a clinical dashboard — and the action colour is a
 * burnt orange that is appetising rather than sporty.
 *
 * The three macro hues separate on *lightness* as well as hue (plum dark, moss
 * mid, wheat light). That means they stay distinguishable in greyscale and under
 * deuteranopia, where three colours of equal lightness would collapse into one.
 */
const palette = {
  /** Warm near-black. Text and dark surfaces. Warm rather than blue-black so it sits with `paper`. */
  ink: '#1A1714',
  /** Warm off-white. The app background. */
  paper: '#FBF8F3',
  /** Burnt orange. Primary action and brand. */
  clay: '#C0562A',
  /** Protein. */
  moss: '#4F6F52',
  /** Carbohydrate. */
  wheat: '#D4A03C',
  /** Fat. */
  plum: '#7C4B6B',
} as const;

/** `ink` as an rgb triple, so neutrals can be derived as opacities of it. */
const INK_RGB = '26, 23, 20';

export const color = {
  ...palette,

  /**
   * Neutrals are `ink` at fixed opacities rather than additional hex values.
   * Six greys picked by eye would drift out of tune with the warm base; opacities
   * of the text colour stay in tune by construction.
   */
  inkMuted: `rgba(${INK_RGB}, 0.64)`,
  inkFaint: `rgba(${INK_RGB}, 0.40)`,
  hairline: `rgba(${INK_RGB}, 0.10)`,
  inkWash: `rgba(${INK_RGB}, 0.04)`,

  /** Cards and sheets: a half-step lighter than `paper` so they lift without a shadow. */
  surface: '#FFFDFA',

  /**
   * A darkened shade of `clay`, not a seventh brand colour. Used for pressed
   * states and for error accents. Reusing the accent hue for errors keeps the
   * palette tight; the darker value is what separates "danger" from "action".
   */
  clayDeep: '#8E3D1B',

  /** Text and icons on top of `clay` or `ink`. */
  onDark: '#FBF8F3',
} as const;

/**
 * Spacing scale. Multiples of 4 with a 12 inserted, because 8 -> 16 is too big a
 * jump for the gap between a label and its value.
 */
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
 * Radius scale. Kept tighter than the current app-design fashion: this is a
 * dense, information-first app, and heavily rounded cards waste horizontal space
 * and make list rows read as loose.
 */
export const radius = {
  sm: 6,
  md: 10,
  lg: 16,
  xl: 24,
  pill: 999,
} as const;

/** Minimum touch target. Below this, taps start missing — non-negotiable, not a style choice. */
export const HIT_SLOP_MIN = 44;

export type SpaceToken = keyof typeof space;
export type RadiusToken = keyof typeof radius;
export type ColorToken = keyof typeof color;
