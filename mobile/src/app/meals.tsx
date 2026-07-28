/**
 * Saved meals.
 *
 * The point of the whole feature: a plate you eat repeatedly gets composed once
 * and logged in two taps from then on. A meal is not a recipe — there are no
 * servings to divide, because nobody portions out their own breakfast.
 */

import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { type Meal, deleteMeal, listMeals, logMeal } from '@/api/catalogue';
import { ApiError } from '@/api/client';
import { MEAL_SLOTS, type MealSlot } from '@/api/diary';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { FoodThumb } from '@/components/food-thumb';
import { EnterUp, PressableScale } from '@/components/motion';
import { Screen } from '@/components/screen';
import { draftActions } from '@/features/meals/draft-store';
import { useT } from '@/i18n';
import { HOME } from '@/routes';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; meals: Meal[] }
  | { kind: 'error'; message: string };

export default function MealsScreen() {
  const router = useRouter();
  const t = useT();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [logging, setLogging] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setState({ kind: 'ready', meals: await listMeals() });
    } catch (caught) {
      setState({
        kind: 'error',
        message: caught instanceof ApiError ? caught.userMessage : 'Could not load your meals.',
      });
    }
  }, []);

  // Refetch on focus rather than on mount. Coming back from the builder having
  // just saved a meal must show it — a mount-only fetch shows the list as it was
  // before, which reads as the save having failed.
  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const askSlotAndLog = (meal: Meal) => {
    Alert.alert(meal.name, t('meals.whichMeal'), [
      ...MEAL_SLOTS.map((slot) => ({
        text: t(`slot.${slot}`),
        onPress: () => void send(meal, slot),
      })),
      { text: t('common.cancel'), style: 'cancel' as const },
    ]);
  };

  const send = async (meal: Meal, slot: MealSlot) => {
    setLogging(meal.id);
    try {
      await logMeal(meal.id, slot);
      router.replace(HOME);
    } catch (caught) {
      Alert.alert(
        'Could not log that',
        caught instanceof ApiError ? caught.userMessage : 'Please try again.',
      );
    } finally {
      setLogging(null);
    }
  };

  const confirmDelete = (meal: Meal) => {
    Alert.alert(t('meals.deleteTitle'), t('meals.deleteBody', { name: meal.name }), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('common.delete'),
        style: 'destructive',
        onPress: () => {
          void (async () => {
            try {
              await deleteMeal(meal.id);
              await load();
            } catch {
              Alert.alert('Could not delete that meal.');
            }
          })();
        },
      },
    ]);
  };

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={text.overline}>{t('meals.title')}</Text>
        <Pressable onPress={() => router.back()} accessibilityRole="button" style={styles.cancel}>
          <Text style={styles.cancelLabel}>{t('common.close')}</Text>
        </Pressable>
      </View>

      {state.kind === 'loading' && (
        <View style={styles.centered}>
          <ActivityIndicator color={color.accent} />
        </View>
      )}

      {state.kind === 'error' && (
        <View style={styles.centered}>
          <Text style={text.title}>{t('catalogue.cantLoad')}</Text>
          <Text style={[text.bodyMuted, styles.centeredBody]}>{state.message}</Text>
        </View>
      )}

      {state.kind === 'ready' && (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
          {state.meals.length === 0 ? (
            <View style={styles.empty}>
              <Text style={styles.emptyGlyph}>🍽</Text>
              <Text style={text.title}>{t('meals.emptyTitle')}</Text>
              <Text style={[text.bodyMuted, styles.centeredBody]}>
{t('meals.emptyBody')}
              </Text>
            </View>
          ) : (
            state.meals.map((meal, index) => (
              <EnterUp key={meal.id} index={index}>
                <Card style={styles.card}>
                  <Pressable
                    onPress={() => askSlotAndLog(meal)}
                    onLongPress={() => confirmDelete(meal)}
                    accessibilityRole="button"
                    accessibilityLabel={`Log ${meal.name}`}
                  >
                    <View style={styles.cardHead}>
                      <View style={styles.cardTitles}>
                        <Text style={text.title} numberOfLines={1}>
                          {meal.name}
                        </Text>
                        <Text style={text.bodyMuted}>
                          {t('meals.ingredientCount', {
                            count: meal.items.length,
                            grams: Math.round(meal.totals.total_grams),
                          })}
                        </Text>
                      </View>
                      <View style={styles.kcalBlock}>
                        <Text style={styles.kcal}>{Math.round(meal.totals.kcal)}</Text>
                        <Text style={styles.kcalUnit}>kcal</Text>
                      </View>
                    </View>

                    <View style={styles.thumbs}>
                      {meal.items.slice(0, 8).map((item) => (
                        <FoodThumb
                          key={item.slug}
                          emoji={item.emoji}
                          photo={item.photo}
                          size={30}
                        />
                      ))}
                      {meal.items.length > 8 && (
                        <Text style={styles.more}>+{meal.items.length - 8}</Text>
                      )}
                    </View>

                    <View style={styles.macros}>
                      <Macro label={t('common.protein')} value={meal.totals.protein_g} tint={color.proteinTint} />
                      <Macro label={t('common.carbs')} value={meal.totals.carbs_g} tint={color.carbsTint} />
                      <Macro label={t('common.fat')} value={meal.totals.fat_g} tint={color.fatTint} />
                    </View>

                    {/* Mongo has no foreign keys, so an ingredient can genuinely
                        vanish from under a saved meal. Saying so is the only
                        honest option — the calories below would otherwise have
                        quietly fallen with no explanation. */}
                    {meal.missing_slugs.length > 0 && (
                      <Text style={styles.warning}>
                        {/* Separate strings for one and many rather than an
                            English-shaped "s" suffix. French pluralises
                            differently ("figure" vs "figurent"), and building a
                            sentence out of fragments only works in the language
                            it was written for. */}
                        {meal.missing_slugs.length === 1
                          ? t('meals.missingOne')
                          : t('meals.missingMany', { count: meal.missing_slugs.length })}
                      </Text>
                    )}
                  </Pressable>

                  <View style={styles.cardActions}>
                    <PressableScale
                      onPress={() => {
                        draftActions.reset({
                          id: meal.id,
                          name: meal.name,
                          items: meal.items.map((item) => ({
                            slug: item.slug,
                            nameEn: item.name_en,
                            nameFr: item.name_fr,
                            emoji: item.emoji,
                            unit: item.unit,
                            gramsPerUnit: item.grams_per_unit,
                            amount: item.amount,
                            kcal: item.kcal_per_100g,
                            protein_g: item.protein_g_per_100g,
                            carbs_g: item.carbs_g_per_100g,
                            fat_g: item.fat_g_per_100g,
                          })),
                        });
                        router.push('/meal-builder');
                      }}
                      accessibilityRole="button"
                      style={styles.secondaryAction}
                    >
                      <Text style={styles.secondaryLabel}>{t('common.edit')}</Text>
                    </PressableScale>
                    <Text style={styles.hint}>
                      {logging === meal.id ? t('meals.logging') : t('meals.tapToLog')}
                    </Text>
                  </View>
                </Card>
              </EnterUp>
            ))
          )}

          <Button
            label={t('meals.compose')}
            onPress={() => {
              draftActions.reset();
              router.push('/meal-builder');
            }}
          />
        </ScrollView>
      )}
    </Screen>
  );
}

function Macro({ label, value, tint }: { label: string; value: number; tint: string }) {
  return (
    <View style={[styles.macro, { backgroundColor: tint }]}>
      <Text style={styles.macroValue}>{Math.round(value)} g</Text>
      <Text style={styles.macroLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.md,
  },
  cancel: { minHeight: HIT_SLOP_MIN, justifyContent: 'center', paddingLeft: space.md },
  cancelLabel: { ...text.label, color: color.accent },

  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.sm },
  centeredBody: { textAlign: 'center', lineHeight: 21 },
  empty: { alignItems: 'center', gap: space.md, paddingVertical: space.xxxl },
  emptyGlyph: { fontSize: 44 },

  scroll: { paddingBottom: space.xxl, gap: space.md },
  card: { gap: space.md },
  cardHead: { flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  cardTitles: { flex: 1, gap: 2 },
  kcalBlock: { alignItems: 'flex-end' },
  kcal: { ...text.numeric, fontSize: 24 },
  kcalUnit: { ...text.bodyMuted, fontSize: 11 },

  thumbs: { flexDirection: 'row', alignItems: 'center', gap: space.xs, marginTop: space.sm },
  more: { ...text.bodyMuted, fontSize: 12, marginLeft: space.xs },

  macros: { flexDirection: 'row', gap: space.sm, marginTop: space.sm },
  macro: { flex: 1, alignItems: 'center', paddingVertical: space.sm, borderRadius: radius.sm },
  macroValue: { ...text.label, fontSize: 14 },
  macroLabel: { ...text.overline, fontSize: 9, color: color.inkMuted },

  warning: { ...text.bodyMuted, fontSize: 12, color: color.warning, marginTop: space.sm },

  cardActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.hairline,
    paddingTop: space.md,
  },
  secondaryAction: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    backgroundColor: color.accentTint,
  },
  secondaryLabel: { ...text.label, fontSize: 13, color: color.accentDeep },
  hint: { ...text.bodyMuted, fontSize: 11 },
});
