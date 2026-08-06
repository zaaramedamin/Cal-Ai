/**
 * The recipe builder, shared by create and edit.
 *
 * Totals update live as ingredients are added, which is the point of the screen:
 * a cook adjusting quantities needs to see the effect immediately, not after
 * saving.
 */

import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { apiErrorMessage } from '@/api/errors';
import { createRecipe, deleteRecipe, updateRecipe } from '@/api/recipes';
import { Button } from '@/components/button';
import { MacroBar } from '@/components/macro-bar';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { draftActions, draftTotals, useDraftRecipe } from '@/features/recipes/draft-store';
import { useT } from '@/i18n';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export function RecipeBuilder() {
  const router = useRouter();
  const t = useT();
  const draft = useDraftRecipe();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { total, perServing } = draftTotals(draft);
  const canSave = draft.name.trim().length > 0 && draft.ingredients.length > 0;

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      const input = {
        name: draft.name.trim(),
        servings: Math.max(1, Math.round(draft.servings)),
        ingredients: draft.ingredients.map((item) => ({
          food_id: item.foodId,
          grams: item.grams,
        })),
      };
      if (draft.id) await updateRecipe(draft.id, input);
      else await createRecipe(input);

      draftActions.reset();
      router.replace('/recipes');
    } catch (caught) {
      setError(apiErrorMessage(t, caught, 'recipe.saveFailed'));
    } finally {
      setSaving(false);
    }
  }

  function handleDelete() {
    if (!draft.id) return;
    Alert.alert(t('recipe.deleteTitle'), t('recipe.deleteBody', { name: draft.name }), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('common.delete'),
        style: 'destructive',
        onPress: () => {
          void (async () => {
            try {
              await deleteRecipe(draft.id!);
              draftActions.reset();
              router.replace('/recipes');
            } catch {
              Alert.alert(t('recipe.deleteFailed'), t('recipe.deleteFailedBody'));
            }
          })();
        },
      },
    ]);
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Text style={text.overline}>{draft.id ? t('recipe.edit') : t('recipe.new')}</Text>
            <Pressable onPress={() => router.back()} accessibilityRole="button">
              <Text style={styles.link}>{t('common.cancel')}</Text>
            </Pressable>
          </View>

          <View style={styles.fields}>
            <TextField
              label={t('recipe.name')}
              value={draft.name}
              onChangeText={draftActions.setName}
              placeholder={t('recipe.namePlaceholder')}
              autoCapitalize="sentences"
            />
            <TextField
              label={t('recipe.servings')}
              value={String(draft.servings)}
              onChangeText={(value) => draftActions.setServings(Number(value) || 1)}
              keyboardType="number-pad"
              hint={t('recipe.servingsHint')}
            />
          </View>

          {/* Live totals. Per serving is shown as the hero because that is the
              number the user will actually log against. */}
          <View style={styles.heroBlock}>
            <Text style={text.hero}>{Math.round(perServing.kcal).toLocaleString()}</Text>
            <Text style={text.overline}>
              {t('recipe.kcalPerServing', { total: Math.round(total.kcal).toLocaleString() })}
            </Text>
          </View>

          <MacroBar macros={perServing} scale="hero" showLegend />

          <Text style={[text.overline, styles.sectionLabel]}>
            {t('recipe.ingredients', { count: draft.ingredients.length })}
          </Text>

          {draft.ingredients.length === 0 ? (
            <Text style={styles.emptyText}>{t('recipe.emptyIngredients')}</Text>
          ) : (
            draft.ingredients.map((item) => (
              <View key={item.foodId} style={styles.ingredient}>
                <View style={styles.ingredientText}>
                  <Text style={text.label} numberOfLines={1}>
                    {item.name}
                  </Text>
                  <Text style={styles.ingredientMeta}>
                    {Math.round((item.kcal * item.grams) / 100)} kcal
                    {item.brand ? ` · ${item.brand}` : ''}
                  </Text>
                </View>
                <View style={styles.gramsField}>
                  <TextField
                    label="g"
                    value={String(Math.round(item.grams))}
                    onChangeText={(value) =>
                      draftActions.updateGrams(item.foodId, Number(value) || 0)
                    }
                    keyboardType="number-pad"
                  />
                </View>
                <Pressable
                  onPress={() => draftActions.removeIngredient(item.foodId)}
                  accessibilityRole="button"
                  accessibilityLabel={t('recipe.remove', { name: item.name })}
                  style={styles.remove}
                >
                  <Text style={styles.removeLabel}>×</Text>
                </Pressable>
              </View>
            ))
          )}

          <Pressable
            onPress={() => router.push({ pathname: '/search', params: { mode: 'recipe' } })}
            accessibilityRole="button"
            style={styles.addButton}
          >
            <Text style={styles.addLabel}>{t('recipe.addIngredient')}</Text>
          </Pressable>

          {error && (
            <View style={styles.callout} accessibilityRole="alert">
              <Text style={styles.calloutText}>{error}</Text>
            </View>
          )}

          <View style={styles.actions}>
            <Button
              label={draft.id ? t('recipe.saveChanges') : t('recipe.save')}
              disabled={!canSave}
              loading={saving}
              onPress={() => void handleSave()}
            />
            {draft.id && (
              <Pressable onPress={handleDelete} accessibilityRole="button" style={styles.destroy}>
                <Text style={styles.destroyLabel}>{t('recipe.delete')}</Text>
              </Pressable>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { paddingBottom: space.xxl },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: space.md,
  },
  link: { ...text.label, color: color.clay },
  fields: { gap: space.lg },
  heroBlock: { marginTop: space.xl, marginBottom: space.xl },
  sectionLabel: { marginTop: space.xl, marginBottom: space.sm },
  emptyText: { ...text.bodyMuted, fontSize: 13, paddingVertical: space.sm },
  ingredient: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: space.sm,
    paddingVertical: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.hairline,
  },
  ingredientText: { flex: 1, gap: 2, paddingBottom: space.sm },
  ingredientMeta: { ...text.bodyMuted, fontSize: 12 },
  gramsField: { width: 78 },
  remove: {
    width: HIT_SLOP_MIN,
    height: HIT_SLOP_MIN,
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeLabel: { ...text.heading, color: color.inkFaint, lineHeight: 26 },
  addButton: { paddingVertical: space.md, minHeight: HIT_SLOP_MIN, justifyContent: 'center' },
  addLabel: { ...text.label, color: color.clay },
  callout: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.clayDeep,
  },
  calloutText: { ...text.body, fontSize: 14 },
  actions: { marginTop: space.xl, gap: space.md },
  destroy: { alignSelf: 'center', padding: space.sm },
  destroyLabel: { ...text.label, color: color.clayDeep },
});
