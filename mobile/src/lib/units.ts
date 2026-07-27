/**
 * Display units.
 *
 * **Everything is stored and calculated in metric.** The backend's validation
 * bounds, the Mifflin-St Jeor equation and every stored weight are kg and cm;
 * these functions exist only at the edge, where a user who thinks in pounds
 * types pounds. Converting at the boundary rather than storing a unit preference
 * alongside each number is what stops the app ever having to ask "is this row
 * kg or lbs?" — a question with no good answer once the data exists.
 */

export type HeightUnit = 'cm' | 'ftin';
export type WeightUnit = 'kg' | 'lbs';

const CM_PER_INCH = 2.54;
const KG_PER_LB = 0.45359237;

export const kgToLbs = (kg: number): number => kg / KG_PER_LB;
export const lbsToKg = (lbs: number): number => lbs * KG_PER_LB;
export const cmToInches = (cm: number): number => cm / CM_PER_INCH;
export const inchesToCm = (inches: number): number => inches * CM_PER_INCH;

/** "5ft, 6in" from a total inch count. */
export function formatFeetInches(totalInches: number): string {
  const whole = Math.round(totalInches);
  return `${Math.floor(whole / 12)}ft, ${whole % 12}in`;
}

/**
 * Ruler bounds per unit, derived from the server's own validation range.
 *
 * Kept in step with `backend/app/nutrition/targets.py`, which rejects heights
 * outside 100–250 cm and weights outside 30–300 kg. Letting the picker offer a
 * value the server will refuse turns a validation rule into a dead end the user
 * cannot see the edge of.
 */
export const HEIGHT_RANGE = {
  cm: { min: 100, max: 250, majorEvery: 10 },
  ftin: { min: Math.ceil(cmToInches(100)), max: Math.floor(cmToInches(250)), majorEvery: 12 },
} as const;

export const WEIGHT_RANGE = {
  kg: { min: 30, max: 300, majorEvery: 10 },
  lbs: { min: Math.ceil(kgToLbs(30)), max: Math.floor(kgToLbs(300)), majorEvery: 10 },
} as const;
