/**
 * Catalogue and meal bindings. Mirrors `backend/app/schemas/catalogue.py`
 * and `meals.py`.
 *
 * The shape to notice is `unit` + `grams_per_unit`. Amounts travel to the server
 * in the food's **own** unit — 2 for eggs, 250 for millilitres of milk — and the
 * server converts. The app never computes grams itself, because the conversion
 * is a fact about the food (milk is denser than water, oil is lighter) and a
 * client that did its own arithmetic would be one refactor away from assuming
 * 1 g per ml everywhere.
 *
 * `grams_per_unit` is here only so the portion sheet can *preview* a weight
 * while the user is choosing. The number that gets stored is always the
 * server's.
 */

import { apiRequest } from './client';
import type { DiaryEntry, MealSlot } from './diary';

/** How a food is measured when a person talks about it. */
export type UnitKind = 'g' | 'ml' | 'unit';

export interface CataloguePortion {
  label_en: string;
  label_fr: string;
  /** In the food's own unit: 1 egg, 250 ml, 30 g. */
  amount: number;
  /** What that weighs. Preview only — the server recomputes on log. */
  grams: number;
  is_default: boolean;
}

export interface CatalogueFood {
  slug: string;
  name_en: string;
  name_fr: string;
  category: string;
  emoji: string;
  /** Filename in the catalogue image store, or null while it has no photo. */
  photo: string | null;

  unit: UnitKind;
  grams_per_unit: number;

  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fibre_g: number | null;
  sugars_g: number | null;
  saturated_fat_g: number | null;
  sodium_mg: number | null;

  source: string;
  source_id: string | null;

  portions: CataloguePortion[];
  order: number;
}

export interface CatalogueSection {
  category: string;
  foods: CatalogueFood[];
}

export interface CatalogueResponse {
  sections: CatalogueSection[];
  total: number;
}

export function getCatalogue(): Promise<CatalogueResponse> {
  return apiRequest<CatalogueResponse>('/api/v1/catalogue', { authenticated: true });
}

export function getCatalogueFood(slug: string): Promise<CatalogueFood> {
  return apiRequest<CatalogueFood>(`/api/v1/catalogue/${slug}`, { authenticated: true });
}

export function logCatalogueFood(input: {
  slug: string;
  amount: number;
  mealSlot: MealSlot;
  day?: string;
}): Promise<DiaryEntry> {
  return apiRequest<DiaryEntry>(`/api/v1/catalogue/${input.slug}/log`, {
    method: 'POST',
    authenticated: true,
    body: { amount: input.amount, meal_slot: input.mealSlot, day: input.day },
  });
}

// --------------------------------------------------------------------------- //
// Meals
// --------------------------------------------------------------------------- //

export interface MealItem {
  slug: string;
  name_en: string;
  name_fr: string;
  emoji: string;
  photo: string | null;
  unit: UnitKind;
  /** In the food's own unit, as the user chose it. */
  amount: number;
  grams: number;
  grams_per_unit: number;
  /** This ingredient's contribution to the meal. */
  kcal: number;

  /** Per 100 g, so the builder's live totals stay honest while editing. */
  kcal_per_100g: number;
  protein_g_per_100g: number;
  carbs_g_per_100g: number;
  fat_g_per_100g: number;
}

export interface MealTotals {
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  sugars_g: number | null;
  saturated_fat_g: number | null;
  fibre_g: number | null;
  sodium_mg: number | null;
  total_grams: number;
  /** Nutrients one ingredient does not report, so the figure is a floor. */
  partial: string[];
}

export interface Meal {
  id: string;
  name: string;
  items: MealItem[];
  totals: MealTotals;
  created_at: string;
  /** Ingredients no longer in the catalogue. Shown, never silently dropped. */
  missing_slugs: string[];
}

export interface MealInput {
  name: string;
  items: { slug: string; amount: number }[];
}

export function listMeals(): Promise<Meal[]> {
  return apiRequest<Meal[]>('/api/v1/meals', { authenticated: true });
}

export function getMeal(id: string): Promise<Meal> {
  return apiRequest<Meal>(`/api/v1/meals/${id}`, { authenticated: true });
}

export function createMeal(input: MealInput): Promise<Meal> {
  return apiRequest<Meal>('/api/v1/meals', { method: 'POST', body: input, authenticated: true });
}

export function updateMeal(id: string, input: MealInput): Promise<Meal> {
  return apiRequest<Meal>(`/api/v1/meals/${id}`, {
    method: 'PUT',
    body: input,
    authenticated: true,
  });
}

export function deleteMeal(id: string): Promise<void> {
  return apiRequest<void>(`/api/v1/meals/${id}`, { method: 'DELETE', authenticated: true });
}

export function logMeal(id: string, mealSlot: MealSlot, day?: string): Promise<DiaryEntry> {
  return apiRequest<DiaryEntry>(`/api/v1/meals/${id}/log`, {
    method: 'POST',
    body: { meal_slot: mealSlot, day },
    authenticated: true,
  });
}

// --------------------------------------------------------------------------- //
// Presentation
// --------------------------------------------------------------------------- //

/** The suffix shown beside an amount field: "g", "ml", or nothing for counts. */
export function unitSuffix(unit: UnitKind): string {
  return unit === 'unit' ? '' : unit;
}

/**
 * Sensible steps for the +/- buttons on the portion sheet.
 *
 * Per unit, because one step does not fit all: nudging milk by 1 ml is useless
 * and nudging eggs by 25 is absurd. Halves for countables so half an avocado
 * stays reachable.
 */
export function amountStep(unit: UnitKind): number {
  if (unit === 'unit') return 0.5;
  if (unit === 'ml') return 25;
  return 10;
}

/** Trims the trailing zero so 2 reads as "2" and 0.5 survives as "0.5". */
export function formatAmount(amount: number): string {
  return Number.isInteger(amount) ? String(amount) : String(Number(amount.toFixed(2)));
}
