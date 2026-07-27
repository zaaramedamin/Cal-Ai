/**
 * Recipe bindings. Mirrors `backend/app/schemas/recipe.py`.
 */

import { apiRequest } from './client';
import type { DiaryEntry, MealSlot } from './diary';

export interface RecipeIngredient {
  id: string;
  food_id: string;
  food_name: string;
  food_brand: string | null;
  grams: number;
  /** This ingredient's contribution at the quantity used. */
  kcal: number;
  kcal_per_100g: number;
  protein_g_per_100g: number;
  carbs_g_per_100g: number;
  fat_g_per_100g: number;
}

export interface RecipeNutrition {
  total_grams: number;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  sugars_g: number | null;
  saturated_fat_g: number | null;
  fibre_g: number | null;
  sodium_mg: number | null;
  partial: string[];
}

export interface Recipe {
  id: string;
  name: string;
  servings: number;
  ingredients: RecipeIngredient[];
  total: RecipeNutrition;
  per_serving: RecipeNutrition;
}

export interface RecipeSummary {
  id: string;
  name: string;
  servings: number;
  ingredient_count: number;
  kcal_per_serving: number;
  protein_g_per_serving: number;
  carbs_g_per_serving: number;
  fat_g_per_serving: number;
}

export interface RecipeInput {
  name: string;
  servings: number;
  ingredients: { food_id: string; grams: number }[];
}

export function listRecipes(): Promise<RecipeSummary[]> {
  return apiRequest<RecipeSummary[]>('/api/v1/recipes', { authenticated: true });
}

export function getRecipe(id: string): Promise<Recipe> {
  return apiRequest<Recipe>(`/api/v1/recipes/${id}`, { authenticated: true });
}

export function createRecipe(input: RecipeInput): Promise<Recipe> {
  return apiRequest<Recipe>('/api/v1/recipes', {
    method: 'POST',
    body: input,
    authenticated: true,
  });
}

export function updateRecipe(id: string, input: RecipeInput): Promise<Recipe> {
  return apiRequest<Recipe>(`/api/v1/recipes/${id}`, {
    method: 'PUT',
    body: input,
    authenticated: true,
  });
}

export function deleteRecipe(id: string): Promise<void> {
  return apiRequest<void>(`/api/v1/recipes/${id}`, { method: 'DELETE', authenticated: true });
}

export function logRecipe(
  id: string,
  servings: number,
  mealSlot: MealSlot,
  day?: string,
): Promise<DiaryEntry> {
  const params = new URLSearchParams({ meal_slot: mealSlot });
  if (day) params.set('day', day);
  return apiRequest<DiaryEntry>(`/api/v1/recipes/${id}/log?${params.toString()}`, {
    method: 'POST',
    body: { servings },
    authenticated: true,
  });
}
