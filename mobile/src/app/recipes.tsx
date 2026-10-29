/**
 * Saved recipes.
 *
 * A recipe logs exactly like a food does — that is the point of the phase. From
 * here, tapping one opens it for editing; the diary's add flow is where you log
 * a portion.
 */

import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { apiErrorMessage } from '@/api/errors';
import { type RecipeSummary, listRecipes } from '@/api/recipes';
import { Button } from '@/components/button';
import { MacroBar } from '@/components/macro-bar';
import { Screen } from '@/components/screen';
import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function RecipeListScreen() {
  const router = useRouter();
  const t = useT();
  const [recipes, setRecipes] = useState<RecipeSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      (async () => {
        try {
          const loaded = await listRecipes();
          if (!cancelled) setRecipes(loaded);
        } catch (caught) {
          if (!cancelled) {
            setError(apiErrorMessage(t, caught, 'recipes.loadFailed'));
          }
        }
      })();
      return () => {
        cancelled = true;
      };
    }, [t]),
  );

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={text.overline}>{t('recipes.eyebrow')}</Text>
        <Pressable onPress={() => router.back()} accessibilityRole="button">
          <Text style={styles.link}>{t('common.done')}</Text>
        </Pressable>
      </View>
      <Text style={text.title}>{t('recipes.title')}</Text>

      {error && (
        <View style={styles.callout} accessibilityRole="alert">
          <Text style={styles.calloutText}>{error}</Text>
        </View>
      )}

      {recipes !== null && recipes.length === 0 && (
        <View style={styles.empty}>
          <Text style={text.heading}>{t('recipes.emptyTitle')}</Text>
          <Text style={[text.bodyMuted, styles.emptyBody]}>{t('recipes.emptyBody')}</Text>
        </View>
      )}

      {recipes && recipes.length > 0 && (
        <FlatList
          data={recipes}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => router.push({ pathname: '/recipe/[id]', params: { id: item.id } })}
              accessibilityRole="button"
              style={styles.row}
            >
              <View style={styles.rowText}>
                <Text style={text.label} numberOfLines={1}>
                  {item.name}
                </Text>
                <Text style={styles.rowMeta}>
                  {item.ingredient_count === 1
                    ? t('recipes.ingredientsOne')
                    : t('recipes.ingredientsMany', { count: item.ingredient_count })}
                  {' · '}
                  {item.servings === 1
                    ? t('recipes.servingsOne')
                    : t('recipes.servingsMany', { count: item.servings })}
                </Text>
                <View style={styles.rowBar}>
                  <MacroBar
                    macros={{
                      protein_g: item.protein_g_per_serving,
                      carbs_g: item.carbs_g_per_serving,
                      fat_g: item.fat_g_per_serving,
                    }}
                    scale="row"
                  />
                </View>
              </View>
              <View style={styles.rowRight}>
                <Text style={text.numeric}>{Math.round(item.kcal_per_serving)}</Text>
                <Text style={styles.perServing}>{t('recipes.perServing')}</Text>
              </View>
            </Pressable>
          )}
        />
      )}

      <View style={styles.actions}>
        <Button label={t('recipes.new')} onPress={() => router.push('/recipe/new')} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: space.xs,
  },
  link: { ...text.label, color: color.accent },
  list: { paddingVertical: space.lg },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.hairline,
  },
  rowText: { flex: 1, gap: 3 },
  rowMeta: { ...text.bodyMuted, fontSize: 12 },
  rowBar: { marginTop: space.xs },
  rowRight: { alignItems: 'flex-end' },
  perServing: { ...text.bodyMuted, fontSize: 11 },
  empty: { flex: 1, justifyContent: 'center', gap: space.sm },
  emptyBody: { lineHeight: 21 },
  actions: { marginTop: space.lg },
  callout: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.dangerTint,
    borderLeftWidth: 3,
    borderLeftColor: color.danger,
  },
  calloutText: { ...text.body, fontSize: 14 },
});
