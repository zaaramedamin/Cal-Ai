/**
 * The recipe being built.
 *
 * Module-level rather than React state, because adding an ingredient means
 * navigating away to the food search and back — and component state does not
 * survive that. React context would work only if every participating screen sat
 * under one provider, which the shared search screen does not.
 *
 * `useSyncExternalStore` is React's supported way to subscribe to a store
 * outside React. It avoids the tearing that a hand-rolled
 * useEffect-plus-setState subscription can produce during concurrent rendering.
 */

import { useSyncExternalStore } from 'react';

export interface DraftIngredient {
  foodId: string;
  name: string;
  brand: string | null;
  grams: number;
  /** Per 100 g, so totals can be recomputed live without a round trip. */
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
}

export interface DraftRecipe {
  /** Set when editing an existing recipe; null when creating one. */
  id: string | null;
  name: string;
  servings: number;
  ingredients: DraftIngredient[];
}

const EMPTY: DraftRecipe = { id: null, name: '', servings: 1, ingredients: [] };

let draft: DraftRecipe = EMPTY;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useDraftRecipe(): DraftRecipe {
  return useSyncExternalStore(
    subscribe,
    () => draft,
    () => draft,
  );
}

export const draftActions = {
  reset(initial?: Partial<DraftRecipe>): void {
    draft = { ...EMPTY, ingredients: [], ...initial };
    emit();
  },

  setName(name: string): void {
    draft = { ...draft, name };
    emit();
  },

  setServings(servings: number): void {
    draft = { ...draft, servings };
    emit();
  },

  addIngredient(ingredient: DraftIngredient): void {
    // Adding a food already present merges the quantities rather than creating a
    // duplicate row. The backend rejects duplicates outright, and two identical
    // lines are invisible in a list while silently doubling a total.
    const existing = draft.ingredients.findIndex((item) => item.foodId === ingredient.foodId);
    if (existing >= 0) {
      const merged = [...draft.ingredients];
      merged[existing] = {
        ...merged[existing],
        grams: merged[existing].grams + ingredient.grams,
      };
      draft = { ...draft, ingredients: merged };
    } else {
      draft = { ...draft, ingredients: [...draft.ingredients, ingredient] };
    }
    emit();
  },

  updateGrams(foodId: string, grams: number): void {
    draft = {
      ...draft,
      ingredients: draft.ingredients.map((item) =>
        item.foodId === foodId ? { ...item, grams } : item,
      ),
    };
    emit();
  },

  removeIngredient(foodId: string): void {
    draft = {
      ...draft,
      ingredients: draft.ingredients.filter((item) => item.foodId !== foodId),
    };
    emit();
  },
};

/**
 * Live totals for the whole recipe and one serving.
 *
 * Computed on the device so the numbers move as ingredients are added, with no
 * round trip. The backend recomputes independently on save — this is for
 * feedback, never the stored truth.
 */
export function draftTotals(recipe: DraftRecipe) {
  const total = recipe.ingredients.reduce(
    (sum, item) => {
      const factor = item.grams / 100;
      return {
        grams: sum.grams + item.grams,
        kcal: sum.kcal + item.kcal * factor,
        protein_g: sum.protein_g + item.protein_g * factor,
        carbs_g: sum.carbs_g + item.carbs_g * factor,
        fat_g: sum.fat_g + item.fat_g * factor,
      };
    },
    { grams: 0, kcal: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
  );

  const servings = Math.max(1, recipe.servings);
  return {
    total,
    perServing: {
      grams: total.grams / servings,
      kcal: total.kcal / servings,
      protein_g: total.protein_g / servings,
      carbs_g: total.carbs_g / servings,
      fat_g: total.fat_g / servings,
    },
  };
}
