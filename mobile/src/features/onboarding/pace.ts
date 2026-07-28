/**
 * Turning "how fast" into something a person can picture.
 *
 * A rate in kilograms per week is honest but abstract. What someone actually
 * wants to know is *when they arrive* and *what it costs per day*, so this
 * module converts the rate into both, and the picker shows those rather than
 * the bare number.
 *
 * All of this is presentation. The server recomputes the calorie target from the
 * rate independently, and its answer is the one that counts — these figures
 * exist so the choice is not made blind.
 */

/**
 * Energy in a kilogram of body fat.
 *
 * Kept identical to `KCAL_PER_KG_BODY_FAT` in `backend/app/nutrition/targets.py`.
 * Duplicated rather than fetched because it is a physical constant used here
 * only to preview a number the server will calculate properly — but it is
 * duplicated *knowingly*, which is why both sides name the other.
 */
export const KCAL_PER_KG_BODY_FAT = 7700;

/** Beyond this fraction of bodyweight per week, more of the loss is muscle. */
export const MAX_SAFE_WEEKLY_CHANGE_FRACTION = 0.01;

export interface PaceOption {
  /** kg per week, always positive. The goal supplies the direction. */
  rateKg: number;
  label: string;
  /** Roughly what it costs or adds per day. */
  dailyKcal: number;
  /** Weeks to reach the target weight, or null when there is no target. */
  weeks: number | null;
  /** True when this pace exceeds 1% of bodyweight per week. */
  aggressive: boolean;
}

/** The rates offered. Quarter-kilogram steps are fine enough to feel chosen. */
export const PACE_RATES = [0.25, 0.5, 0.75, 1.0] as const;

export function dailyKcalFor(rateKg: number): number {
  return Math.round((rateKg * KCAL_PER_KG_BODY_FAT) / 7);
}

/**
 * How many weeks to cover the distance between two weights at a given rate.
 *
 * Returns null when there is nothing to project — no target, or a target the
 * user is already at. Deliberately *not* clamped to something reassuring: if the
 * honest answer is 78 weeks, that is what the picker should say, because it is
 * the number that makes a slower pace an informed choice rather than a
 * discouraging one.
 */
export function weeksToTarget(
  currentKg: number,
  targetKg: number | null,
  rateKg: number,
): number | null {
  if (targetKg === null || rateKg <= 0) return null;
  const distance = Math.abs(currentKg - targetKg);
  if (distance < 0.1) return null;
  return Math.ceil(distance / rateKg);
}

/** The date `weeks` from today, as a local `YYYY-MM-DD`. */
export function dateInWeeks(weeks: number, from: Date = new Date()): Date {
  const arrival = new Date(from);
  arrival.setDate(arrival.getDate() + weeks * 7);
  return arrival;
}

/**
 * "by March 2027" — month precision, not a day.
 *
 * A precise date would be a lie dressed as a fact. This projection assumes a
 * constant rate, perfect adherence and a tidy 7,700 kcal per kilogram; none of
 * those hold, and "14 March" invites someone to believe the app knows something
 * it does not.
 */
export function formatArrival(date: Date, locale = 'en'): string {
  return date.toLocaleDateString(locale, { month: 'long', year: 'numeric' });
}

export function buildPaceOptions(
  currentKg: number,
  targetKg: number | null,
  locale = 'en',
): PaceOption[] {
  const safeMax = currentKg * MAX_SAFE_WEEKLY_CHANGE_FRACTION;

  return PACE_RATES.map((rateKg) => {
    const weeks = weeksToTarget(currentKg, targetKg, rateKg);
    return {
      rateKg,
      label:
        weeks === null
          ? `${rateKg} kg per week`
          : `${rateKg} kg per week · ${formatArrival(dateInWeeks(weeks), locale)}`,
      dailyKcal: dailyKcalFor(rateKg),
      weeks,
      aggressive: rateKg > safeMax,
    };
  });
}
