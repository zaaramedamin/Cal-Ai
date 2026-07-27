/**
 * Meal photo scanning bindings.
 *
 * Mirrors `backend/app/schemas/scan.py`.
 *
 * Read `ScannedItem` and notice the division of labour. `detected_name` and
 * `estimated_grams` are the AI's contribution — a guess about what is on the
 * plate. `match` is a row from the USDA-backed database, and it is the only
 * place a calorie appears. Nothing here carries a nutrition value the model
 * made up, because the model is never asked for one.
 */

import { apiRequest } from './client';
import type { FoodSearchResult } from './diary';

export interface ScannedItem {
  /** What the model called it, kept verbatim even when we could not match it. */
  detected_name: string;
  /** The model's visual estimate. Editable before anything is logged. */
  estimated_grams: number;
  /** The model's own certainty, 0–1. A hint for the user, never a gate. */
  confidence: number;
  /**
   * null when nothing matched and nothing could be estimated.
   *
   * When `match.source` is `ai_estimate` the numbers came from the model rather
   * than a measurement. Check it before rendering — see `isEstimate` below.
   */
  match: FoodSearchResult | null;
}

export interface ScanResponse {
  items: ScannedItem[];
  /** The model's caveats: "sauce not visible", "no food in this photo". */
  notes: string;
  unmatched_count: number;
  /** How many items carry AI-estimated numbers rather than database ones. */
  estimated_count: number;
}

/**
 * Whether a match's numbers were estimated rather than measured.
 *
 * A named predicate rather than an inline string comparison scattered across
 * screens: every place that shows these numbers has to show the warning too,
 * and one function is something you can search for to check that.
 */
export function isEstimate(match: FoodSearchResult | null): boolean {
  return match?.source === 'ai_estimate';
}

/**
 * Vision inference is slow — several seconds is normal, and the request also
 * waits on food matching behind it. The default 10s timeout would abort a
 * perfectly healthy scan, so this one gets its own budget.
 */
const SCAN_TIMEOUT_MS = 45_000;

export function scanMeal(input: {
  imageBase64: string;
  mediaType?: string;
}): Promise<ScanResponse> {
  return apiRequest<ScanResponse>('/api/v1/scan', {
    method: 'POST',
    authenticated: true,
    timeoutMs: SCAN_TIMEOUT_MS,
    body: {
      image_base64: input.imageBase64,
      media_type: input.mediaType ?? 'image/jpeg',
    },
  });
}
