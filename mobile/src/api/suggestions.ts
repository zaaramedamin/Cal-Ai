/**
 * Meal suggestion bindings. Mirrors `backend/app/api/v1/suggestions.py`.
 *
 * Suggestions are arithmetic over USDA values, not model output — the backend
 * ranks real foods against the calories and macros left in the day. That is why
 * every suggestion carries a `reason` in the user's own numbers: a
 * recommendation without one is indistinguishable from an advertisement.
 */

import { apiRequest } from './client';
import type { FoodSearchResult } from './diary';

export interface Suggestion {
  food: FoodSearchResult;
  /** Portion already sized to what is left of the day. */
  grams: number;
  kcal: number;
  reason: string;
}

export interface SuggestionsResponse {
  suggestions: Suggestion[];
  remaining_kcal: number;
  remaining_protein_g: number;
  remaining_carbs_g: number;
  remaining_fat_g: number;
  /** Why there is nothing to suggest, when there is nothing to suggest. */
  note: string | null;
}

export function getSuggestions(): Promise<SuggestionsResponse> {
  return apiRequest<SuggestionsResponse>('/api/v1/suggestions', { authenticated: true });
}
