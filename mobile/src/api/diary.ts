/**
 * Food search and diary bindings.
 *
 * Mirrors `backend/app/schemas/food.py` and `diary.py`.
 *
 * Note every optional nutrient is `number | null`, never `number`. That null
 * travels all the way to the screen and renders as an em dash, meaning "the
 * source did not report this" — a different and more honest claim than "there is
 * none of it".
 */

import { apiRequest } from './client';
import type { MacroTargets } from './profile';

export type MealSlot = 'breakfast' | 'lunch' | 'dinner' | 'snack';

export const MEAL_SLOTS: readonly MealSlot[] = ['breakfast', 'lunch', 'dinner', 'snack'];

export const MEAL_LABELS: Record<MealSlot, string> = {
  breakfast: 'Breakfast',
  lunch: 'Lunch',
  dinner: 'Dinner',
  snack: 'Snacks',
};

export interface FoodSearchResult {
  id: string;
  source: string;
  name: string;
  brand: string | null;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
}

export interface FoodSearchResponse {
  query: string;
  results: FoodSearchResult[];
  upstream_unavailable: boolean;
}

export interface Portion {
  id: string;
  label: string;
  grams: number;
  is_default: boolean;
}

export interface Food extends FoodSearchResult {
  source_id: string;
  is_liquid: boolean;
  sugars_g: number | null;
  saturated_fat_g: number | null;
  fibre_g: number | null;
  sodium_mg: number | null;
  portions: Portion[];
}

export interface DiaryEntry {
  id: string;
  local_date: string;
  meal_slot: MealSlot;
  food_id: string | null;
  recipe_id: string | null;
  food_name: string;
  food_brand: string | null;
  quantity_grams: number;
  /** Set only for recipe entries — what the user chose ("1.5 servings"). */
  servings: number | null;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  sugars_g: number | null;
  saturated_fat_g: number | null;
  fibre_g: number | null;
  sodium_mg: number | null;
  logged_at: string;
}

export interface NutrientTotals {
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  sugars_g: number | null;
  saturated_fat_g: number | null;
  fibre_g: number | null;
  sodium_mg: number | null;
  /** Nutrients where at least one entry had no data, so the total is a floor. */
  partial: string[];
}

export interface MealGroup {
  meal_slot: MealSlot;
  entries: DiaryEntry[];
  totals: NutrientTotals;
}

export interface DaySummary {
  local_date: string;
  meals: MealGroup[];
  totals: NutrientTotals;
  target_calories: number;
  target_macros: MacroTargets;
  remaining_calories: number;
}

export function searchFoods(query: string): Promise<FoodSearchResponse> {
  return apiRequest<FoodSearchResponse>(
    `/api/v1/foods/search?q=${encodeURIComponent(query)}`,
    { authenticated: true, timeoutMs: 20_000 },
  );
}

export function getFood(foodId: string): Promise<Food> {
  return apiRequest<Food>(`/api/v1/foods/${foodId}`, { authenticated: true });
}

export function getDay(day?: string): Promise<DaySummary> {
  const suffix = day ? `?day=${day}` : '';
  return apiRequest<DaySummary>(`/api/v1/diary${suffix}`, { authenticated: true });
}

export function logFood(input: {
  foodId: string;
  mealSlot: MealSlot;
  quantityGrams: number;
  localDate?: string;
}): Promise<DiaryEntry> {
  return apiRequest<DiaryEntry>('/api/v1/diary', {
    method: 'POST',
    authenticated: true,
    body: {
      food_id: input.foodId,
      meal_slot: input.mealSlot,
      quantity_grams: input.quantityGrams,
      local_date: input.localDate,
    },
  });
}

export function deleteEntry(entryId: string): Promise<void> {
  return apiRequest<void>(`/api/v1/diary/${entryId}`, {
    method: 'DELETE',
    authenticated: true,
  });
}

/**
 * Today as a local `YYYY-MM-DD`.
 *
 * Built from the local date parts rather than `toISOString()`, which converts to
 * UTC first — so anyone east of Greenwich in the early morning, or west of it
 * late at night, would get yesterday's or tomorrow's date.
 */
export function localDateString(date: Date = new Date()): string {
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export function addDays(isoDate: string, delta: number): string {
  const [year, month, day] = isoDate.split('-').map(Number);
  // Constructed as a local date, not parsed from the string, which would be
  // treated as UTC midnight and shift the day for most of the world.
  const date = new Date(year, month - 1, day);
  date.setDate(date.getDate() + delta);
  return localDateString(date);
}
