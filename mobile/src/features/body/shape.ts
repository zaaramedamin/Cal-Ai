/**
 * Turning height and weight into a figure.
 *
 * **The decisions here are as much editorial as mathematical**, and they are in
 * their own module so they can be argued with rather than buried in a component.
 *
 * A body avatar in a calorie tracker is the single feature most capable of doing
 * harm. Someone opens this app several times a day, often already unhappy with
 * how they look, and a silhouette is a picture of *them*. Three rules follow, and
 * every function below is built around them:
 *
 * 1. **No verdicts.** The figure is a continuous shape, never a category. There
 *    is no threshold it crosses and no word attached to where it sits. A label
 *    reading "obese" on a home screen is not information anybody needs at 8am.
 * 2. **A narrow visual range.** The widest silhouette is 1.45x the narrowest,
 *    not 4x. Enough that a real change is visible over weeks; not so much that
 *    the picture becomes a caricature.
 * 3. **It is a mirror, not a scoreboard.** The shape follows the numbers the
 *    user has already entered. It never implies a target shape, and nothing in
 *    the drawing marks where they "should" be.
 */

/** Body mass index. The user's own numbers, not an invented one. */
export function bmi(weightKg: number, heightCm: number): number {
  const metres = heightCm / 100;
  return weightKg / (metres * metres);
}

/**
 * BMI mapped to 0..1 across the range worth drawing.
 *
 * Clamped at both ends deliberately. Below 15 and above 40 the figure stops
 * changing — partly because the drawing would stop looking like a person, and
 * partly because those are exactly the readings where an app exaggerating the
 * picture would be least welcome.
 */
export const BMI_FLOOR = 15;
export const BMI_CEILING = 40;

export function shapeFactor(weightKg: number, heightCm: number): number {
  const value = bmi(weightKg, heightCm);
  const clamped = Math.min(BMI_CEILING, Math.max(BMI_FLOOR, value));
  return (clamped - BMI_FLOOR) / (BMI_CEILING - BMI_FLOOR);
}

/** Narrowest and widest torso multipliers. See rule 2 above. */
export const MIN_WIDTH = 0.82;
export const MAX_WIDTH = 1.19;

export function torsoWidth(weightKg: number, heightCm: number): number {
  return MIN_WIDTH + shapeFactor(weightKg, heightCm) * (MAX_WIDTH - MIN_WIDTH);
}

/**
 * How tall to draw the figure, relative to the frame.
 *
 * A gentler mapping than reality: 150 cm to 200 cm is a 33% difference in life
 * and about 15% here. Drawing it faithfully would leave short users a small
 * figure adrift in white space, which reads as a judgement rather than a fact
 * about the layout.
 *
 * The first attempt damped it to 0.25 and produced a 7% spread — measured across
 * the real range, 0.968 to 1.041, which is not a difference anyone would notice.
 * A height-aware figure whose height is invisible is not height-aware.
 */
export const REFERENCE_HEIGHT_CM = 172;
export const HEIGHT_SENSITIVITY = 0.5;

export function heightScale(heightCm: number): number {
  const ratio = heightCm / REFERENCE_HEIGHT_CM;
  const damped = 1 + (ratio - 1) * HEIGHT_SENSITIVITY;
  return Math.min(1.1, Math.max(0.9, damped));
}

export interface BodyShape {
  /** Torso and limb thickness multiplier. */
  width: number;
  /** Overall figure scale. */
  scale: number;
  /** 0..1 position across the drawn BMI range, for the scale indicator. */
  factor: number;
  bmi: number;
}

export function bodyShape(weightKg: number, heightCm: number): BodyShape {
  return {
    width: torsoWidth(weightKg, heightCm),
    scale: heightScale(heightCm),
    factor: shapeFactor(weightKg, heightCm),
    bmi: bmi(weightKg, heightCm),
  };
}

/**
 * Progress from a starting weight toward a target.
 *
 * Returns 0..1, or null when there is no target or no distance to cover.
 * Clamped at 1 rather than reporting 130%: overshooting a goal weight is not a
 * thing to celebrate with a number, and the caller shows "reached" instead.
 */
export function progressToTarget(
  startKg: number,
  currentKg: number,
  targetKg: number | null,
): number | null {
  if (targetKg === null) return null;
  const total = Math.abs(targetKg - startKg);
  if (total < 0.1) return null;
  const covered = Math.abs(currentKg - startKg);
  return Math.min(1, Math.max(0, covered / total));
}
