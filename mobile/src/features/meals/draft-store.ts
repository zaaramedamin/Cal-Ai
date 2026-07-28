/**
 * The meal being composed.
 *
 * Module-level for the same reason the recipe draft is: adding an ingredient
 * means navigating to the catalogue and back, and component state does not
 * survive that.
 *
 * What differs from the recipe draft is the unit. An ingredient here holds an
 * `amount` in the food's *own* unit — 2 eggs, 250 ml — plus the `gramsPerUnit`
 * needed to preview a weight. The amount is what gets sent; the grams are only
 * ever shown.
 */

import { useSyncExternalStore } from 'react';

import type { CatalogueFood, UnitKind } from '@/api/catalogue';

export interface DraftMealItem {
  slug: string;
  nameEn: string;
  nameFr: string;
  emoji: string;
  unit: UnitKind;
  gramsPerUnit: number;
  /** In the food's own unit. */
  amount: number;
  /** Per 100 g, so totals move live without a round trip. */
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
}

export interface DraftMeal {
  /** Set when editing a saved meal; null when composing a new one. */
  id: string | null;
  name: string;
  items: DraftMealItem[];
}

const EMPTY: DraftMeal = { id: null, name: '', items: [] };

let draft: DraftMeal = EMPTY;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useDraftMeal(): DraftMeal {
  return useSyncExternalStore(
    subscribe,
    () => draft,
    () => draft,
  );
}

/** Turn a catalogue food into a draft row at its default portion. */
export function itemFromFood(food: CatalogueFood, amount?: number): DraftMealItem {
  const preferred = food.portions.find((portion) => portion.is_default) ?? food.portions[0];
  return {
    slug: food.slug,
    nameEn: food.name_en,
    nameFr: food.name_fr,
    emoji: food.emoji,
    unit: food.unit,
    gramsPerUnit: food.grams_per_unit,
    // Falls back to one unit rather than 100, which would mean "100 eggs" for a
    // countable food that somehow shipped with no portions.
    amount: amount ?? preferred?.amount ?? 1,
    kcal: food.kcal,
    protein_g: food.protein_g,
    carbs_g: food.carbs_g,
    fat_g: food.fat_g,
  };
}

export const draftActions = {
  reset(initial?: Partial<DraftMeal>): void {
    draft = { ...EMPTY, items: [], ...initial };
    emit();
  },

  setName(name: string): void {
    draft = { ...draft, name };
    emit();
  },

  addItem(item: DraftMealItem): void {
    // Adding a food already in the meal adjusts that row rather than creating a
    // second one. The backend rejects duplicates outright, and two identical
    // lines are near-invisible in a list while silently doubling a total.
    const existing = draft.items.findIndex((row) => row.slug === item.slug);
    if (existing >= 0) {
      const merged = [...draft.items];
      merged[existing] = { ...merged[existing], amount: merged[existing].amount + item.amount };
      draft = { ...draft, items: merged };
    } else {
      draft = { ...draft, items: [...draft.items, item] };
    }
    emit();
  },

  setAmount(slug: string, amount: number): void {
    draft = {
      ...draft,
      items: draft.items.map((row) => (row.slug === slug ? { ...row, amount } : row)),
    };
    emit();
  },

  removeItem(slug: string): void {
    draft = { ...draft, items: draft.items.filter((row) => row.slug !== slug) };
    emit();
  },
};

/**
 * Live totals as the meal is built.
 *
 * Computed on the device purely so the numbers move while you add ingredients.
 * The backend recomputes independently on save, and its answer is the one that
 * is stored — this never becomes truth.
 */
export function draftTotals(meal: DraftMeal) {
  return meal.items.reduce(
    (sum, item) => {
      const grams = item.amount * item.gramsPerUnit;
      const factor = grams / 100;
      return {
        grams: sum.grams + grams,
        kcal: sum.kcal + item.kcal * factor,
        protein_g: sum.protein_g + item.protein_g * factor,
        carbs_g: sum.carbs_g + item.carbs_g * factor,
        fat_g: sum.fat_g + item.fat_g * factor,
      };
    },
    { grams: 0, kcal: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
  );
}
