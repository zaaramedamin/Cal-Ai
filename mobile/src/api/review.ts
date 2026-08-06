/**
 * Food submission and reporting. Mirrors `backend/app/api/v1/review.py`.
 *
 * Only the user-facing half is here — submitting a food, reporting one, and
 * seeing what came of either. The queue and the decision endpoints are
 * deliberately absent: admin tools do not belong in a binary every user
 * installs, and a client that cannot call them is one that cannot be tricked
 * into calling them.
 */

import { apiRequest } from './client';
import type { Food } from './diary';

export type ReviewStatus = 'private' | 'pending' | 'approved' | 'rejected';

export interface Submission {
  food: Food;
  review_status: ReviewStatus;
  submitted_at: string | null;
  reviewed_at: string | null;
  /** Why it was rejected, or what an admin changed. Written for the author. */
  review_note: string | null;
  /** The screening verdict. Advice for the reviewer, never the decision. */
  llm_verdict: 'plausible' | 'suspect' | 'not_food' | null;
  llm_reason: string | null;
}

/** Offer one of your foods to the shared database. */
export function submitFood(foodId: string): Promise<Submission> {
  return apiRequest<Submission>(`/api/v1/review/foods/${foodId}/submit`, {
    method: 'POST',
    authenticated: true,
    // Screening runs inside the request, so this waits on Gemini.
    timeoutMs: 45_000,
  });
}

export function mySubmissions(): Promise<Submission[]> {
  return apiRequest<Submission[]>('/api/v1/review/foods/mine', { authenticated: true });
}

/* -------------------------------------------------------------------------- */
/* Reports — the other direction: something already in the database is wrong   */
/* -------------------------------------------------------------------------- */

export type ReportReason =
  | 'wrong_numbers'
  | 'wrong_name'
  | 'not_food'
  | 'duplicate'
  | 'other';

/** Ordered as the sheet lists them: most common complaint first. */
export const REPORT_REASONS: ReportReason[] = [
  'wrong_numbers',
  'wrong_name',
  'duplicate',
  'not_food',
  'other',
];

/** Enough of the food to show what the complaint is about. */
export interface ReportedFood {
  id: string;
  name: string;
  brand: string | null;
  source: string;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  withdrawn_reason: string | null;
  /** Whether an admin may edit these numbers. False for USDA and Open Food Facts. */
  correctable: boolean;
}

export interface FoodReport {
  id: string;
  food_id: string;
  food: ReportedFood;
  reason: ReportReason;
  note: string | null;
  status: 'open' | 'accepted' | 'dismissed';
  /** What was done. `corrected` changed the numbers; `withdrawn` pulled the food. */
  resolution: 'corrected' | 'withdrawn' | null;
  /** Written for the person who reported it. */
  resolution_note: string | null;
  created_at: string;
  resolved_at: string | null;
}

/**
 * Say a food is wrong.
 *
 * Filing a report changes nothing about the food — an admin decides. That is
 * the whole design: a report that could edit a nutrition value on its own would
 * hand the number to whoever complained loudest.
 *
 * A 409 means this account already has an open report on this food.
 */
export function reportFood(
  foodId: string,
  reason: ReportReason,
  note?: string,
): Promise<FoodReport> {
  return apiRequest<FoodReport>(`/api/v1/review/foods/${foodId}/report`, {
    method: 'POST',
    authenticated: true,
    body: { reason, note: note?.trim() || null },
  });
}

export function myReports(): Promise<FoodReport[]> {
  return apiRequest<FoodReport[]>('/api/v1/review/reports/mine', { authenticated: true });
}
