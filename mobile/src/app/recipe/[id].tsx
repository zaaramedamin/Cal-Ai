import { useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { getRecipe } from '@/api/recipes';
import { BackHeader } from '@/components/back-header';
import { Screen } from '@/components/screen';
import { draftActions } from '@/features/recipes/draft-store';
import { RecipeBuilder } from '@/features/recipes/recipe-builder';
import { useT } from '@/i18n';
import { space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function EditRecipeScreen() {
  const t = useT();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loaded = useRef(false);

  useEffect(() => {
    // Load once. Re-running after a trip to the food search would discard the
    // ingredient just added and reload the saved version instead.
    if (loaded.current) return;
    loaded.current = true;

    let cancelled = false;
    (async () => {
      try {
        const recipe = await getRecipe(id);
        if (cancelled) return;
        draftActions.reset({
          id: recipe.id,
          name: recipe.name,
          servings: recipe.servings,
          ingredients: recipe.ingredients.map((item) => ({
            foodId: item.food_id,
            name: item.food_name,
            brand: item.food_brand,
            grams: item.grams,
            // Per-100g values come from the API so live editing recalculates
            // correctly without one request per ingredient.
            kcal: item.kcal_per_100g,
            protein_g: item.protein_g_per_100g,
            carbs_g: item.carbs_g_per_100g,
            fat_g: item.fat_g_per_100g,
          })),
        });
        setReady(true);
      } catch {
        if (!cancelled) setError(t('recipe.loadFailed'));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id, t]);

  if (error) {
    return (
      <Screen>
        {/* A dead end without this: the builder's own Cancel never renders on
            the error branch, so a recipe that failed to load trapped you. */}
        <BackHeader />
        <View style={styles.centered}>
          <Text style={text.title}>{t('recipe.cantLoad')}</Text>
          <Text style={text.bodyMuted}>{error}</Text>
        </View>
      </Screen>
    );
  }

  if (!ready) {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={text.bodyMuted}>{t('common.loading')}</Text>
        </View>
      </Screen>
    );
  }

  return <RecipeBuilder />;
}

const styles = StyleSheet.create({
  centered: { flex: 1, justifyContent: 'center', gap: space.sm },
});
