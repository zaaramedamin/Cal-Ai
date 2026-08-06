/**
 * Weight change over several windows, from the series the API already returns.
 *
 * Computed on the client rather than added to the endpoint because the data is
 * already here — a full year of weigh-ins arrives with every progress load, and
 * a second round trip to have the server subtract two numbers would be slower
 * for no gain in truth.
 *
 * **A window with no earlier reading is `null`, not zero.** Those are different
 * facts: zero means "you weighed the same", null means "there is nothing to
 * compare against yet". Showing 0.0 kg for a user who has weighed in once would
 * be a measurement nobody took, and the difference matters most in exactly the
 * first weeks when someone is checking whether the app works.
 */

export interface WeightPoint {
  recorded_on: string;
  weight_kg: number;
}

export interface WeightChange {
  /** Days back, or null for "all time". */
  days: number | null;
  label: string;
  /** Positive is a gain. Null when nothing old enough exists to compare with. */
  deltaKg: number | null;
}

/** The windows shown, matching what a person actually asks about their weight. */
const WINDOWS: { days: number | null; label: string }[] = [
  { days: 3, label: '3 day' },
  { days: 7, label: '7 day' },
  { days: 14, label: '14 day' },
  { days: 30, label: '30 day' },
  { days: 90, label: '90 day' },
  { days: null, label: 'All time' },
];

function daysBetween(from: string, to: string): number {
  // Parsed as UTC midnight on both sides, so a device in a timezone behind UTC
  // cannot make "today" read as yesterday and shift every window by one.
  const start = Date.parse(`${from}T00:00:00Z`);
  const end = Date.parse(`${to}T00:00:00Z`);
  return Math.round((end - start) / 86_400_000);
}

export function weightChanges(series: WeightPoint[]): WeightChange[] {
  if (series.length === 0) {
    return WINDOWS.map((window) => ({ ...window, deltaKg: null }));
  }

  // The series arrives oldest-first; the latest reading is the reference.
  const latest = series[series.length - 1];

  return WINDOWS.map(({ days, label }) => {
    if (days === null) {
      const first = series[0];
      return {
        days,
        label,
        deltaKg: series.length > 1 ? latest.weight_kg - first.weight_kg : null,
      };
    }

    // The oldest reading still inside the window — not the newest one outside
    // it. "Change over 7 days" means against where you were a week ago, and
    // picking the closest reading to the boundary would silently shorten the
    // window whenever someone weighed in irregularly.
    const inWindow = series.filter(
      (point) => daysBetween(point.recorded_on, latest.recorded_on) <= days,
    );

    if (inWindow.length < 2) return { days, label, deltaKg: null };
    return { days, label, deltaKg: latest.weight_kg - inWindow[0].weight_kg };
  });
}

/** How a delta reads: gaining, losing, or genuinely unchanged. */
export function trendOf(deltaKg: number | null): 'up' | 'down' | 'flat' | 'unknown' {
  if (deltaKg === null) return 'unknown';
  // A tenth of a kilo is below what a bathroom scale resolves reliably and well
  // inside daily water swing, so it is reported as no change rather than as a
  // trend the user might act on.
  if (Math.abs(deltaKg) < 0.1) return 'flat';
  return deltaKg > 0 ? 'up' : 'down';
}
