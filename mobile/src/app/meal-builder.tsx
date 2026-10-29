/**
 * Composing a meal from catalogue ingredients.
 *
 * Totals move as you add, computed on the device. That is feedback, not truth —
 * the server recomputes independently on save, and its answer is what gets
 * stored. The device copy exists because a round trip per ingredient would make
 * building a six-item plate feel like filling in a form.
 *
 * Amounts stay in each ingredient's own unit all the way through: 2 eggs, 250 ml
 * of milk, 60 g of oats sit in the same list without anyone converting anything.
 */

import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  type UnitKind,
  amountStep,
  createMeal,
  formatAmount,
  unitSuffix,
  updateMeal,
} from '@/api/catalogue';
import { apiErrorMessage } from '@/api/errors';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { FoodThumb } from '@/components/food-thumb';
import { PressableScale } from '@/components/motion';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import {
  type DraftMealItem,
  draftActions,
  draftTotals,
  useDraftMeal,
} from '@/features/meals/draft-store';
import { useFrench, useT } from '@/i18n';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function MealBuilderScreen() {
  const router = useRouter();
  const draft = useDraftMeal();
  const t = useT();
  const french = useFrench();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totals = draftTotals(draft);
  const editing = draft.id !== null;
  const canSave = draft.name.trim().length > 0 && draft.items.length > 0;

  const save = async () => {
    setSaving(true);
    setError(null);
    const input = {
      name: draft.name.trim(),
      items: draft.items.map((item) => ({ slug: item.slug, amount: item.amount })),
    };
    try {
      if (draft.id) {
        await updateMeal(draft.id, input);
      } else {
        await createMeal(input);
      }
      draftActions.reset();
      router.back();
    } catch (caught) {
      setError(apiErrorMessage(t, caught, 'meals.saveFailed'));
      setSaving(false);
    }
  };

  const discard = () => {
    if (draft.items.length === 0 && !draft.name) {
      router.back();
      return;
    }
    Alert.alert(t('meals.discardTitle'), t('meals.discardBody'), [
      { text: t('meals.keepEditing'), style: 'cancel' },
      {
        text: t('meals.discard'),
        style: 'destructive',
        onPress: () => {
          draftActions.reset();
          router.back();
        },
      },
    ]);
  };

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={text.overline}>{editing ? t('meals.edit') : t('meals.new')}</Text>
        <Pressable onPress={discard} accessibilityRole="button" style={styles.cancel}>
          <Text style={styles.cancelLabel}>{t('common.cancel')}</Text>
        </Pressable>
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        <TextField
          label={t('meals.name')}
          value={draft.name}
          onChangeText={draftActions.setName}
          placeholder={t('meals.namePlaceholder')}
          maxLength={80}
        />

        <Card style={styles.totals}>
          <View style={styles.totalsHead}>
            <Text style={styles.totalsKcal}>{Math.round(totals.kcal)}</Text>
            <Text style={styles.totalsUnit}>kcal</Text>
            <View style={styles.spacer} />
            <Text style={text.bodyMuted}>
              {t('meals.totalGrams', { grams: Math.round(totals.grams) })}
            </Text>
          </View>
          <View style={styles.macros}>
            <Macro label={t('common.protein')} value={totals.protein_g} tint={color.proteinTint} />
            <Macro label={t('common.carbs')} value={totals.carbs_g} tint={color.carbsTint} />
            <Macro label={t('common.fat')} value={totals.fat_g} tint={color.fatTint} />
          </View>
        </Card>

        {draft.items.length === 0 ? (
          <View style={styles.empty}>
            <Text style={text.bodyMuted}>
{t('meals.noIngredients')}
            </Text>
          </View>
        ) : (
          draft.items.map((item) => (
            <IngredientRow key={item.slug} item={item} french={french} />
          ))
        )}

        <Button
          label={t('catalogue.addIngredient')}
          variant="secondary"
          onPress={() => router.push({ pathname: '/catalogue', params: { mode: 'meal' } })}
        />

        {error && (
          <Text style={styles.error} accessibilityRole="alert">
            {error}
          </Text>
        )}

        <Button
          label={editing ? t('meals.saveChanges') : t('meals.save')}
          onPress={() => void save()}
          disabled={!canSave}
          loading={saving}
        />

        {!canSave && draft.items.length > 0 && (
          <Text style={styles.hint}>{t('meals.needsName')}</Text>
        )}
      </ScrollView>
    </Screen>
  );
}

function IngredientRow({ item, french }: { item: DraftMealItem; french: boolean }) {
  const t = useT();
  const name = french ? item.nameFr : item.nameEn;
  const step = amountStep(item.unit);
  const suffix = unitSuffix(item.unit);
  const grams = item.amount * item.gramsPerUnit;

  const nudge = (delta: number) => {
    const next = Math.round((item.amount + delta) / step) * step;
    if (next < step) {
      draftActions.removeItem(item.slug);
      return;
    }
    draftActions.setAmount(item.slug, Number(next.toFixed(2)));
  };

  return (
    <Card style={styles.row} compact>
      <FoodThumb emoji={item.emoji} photo={null} size={36} />

      <View style={styles.rowText}>
        <Text style={text.label} numberOfLines={1}>
          {name}
        </Text>
        <Text style={styles.rowMeta}>
          {Math.round((item.kcal * grams) / 100)} kcal
          {item.unit !== 'g' ? ` · ${Math.round(grams)} g` : ''}
        </Text>
      </View>

      <View style={styles.rowStepper}>
        <Pressable
          onPress={() => nudge(-step)}
          accessibilityRole="button"
          accessibilityLabel={t('a11y.less', { name })}
          style={styles.stepButton}
        >
          <Text style={styles.stepGlyph}>−</Text>
        </Pressable>
        <Text style={styles.rowAmount}>
          {formatAmount(item.amount)}
          {suffix ? ` ${suffix}` : ''}
        </Text>
        <Pressable
          onPress={() => nudge(step)}
          accessibilityRole="button"
          accessibilityLabel={t('a11y.more', { name })}
          style={styles.stepButton}
        >
          <Text style={styles.stepGlyph}>+</Text>
        </Pressable>
      </View>

      <PressableScale
        onPress={() => draftActions.removeItem(item.slug)}
        accessibilityRole="button"
        accessibilityLabel={t('a11y.remove', { name })}
        style={styles.remove}
      >
        <Text style={styles.removeGlyph}>×</Text>
      </PressableScale>
    </Card>
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

/** Kept exported so the unit type stays reachable from tests. */
export type { UnitKind };

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.md,
  },
  cancel: { minHeight: HIT_SLOP_MIN, justifyContent: 'center', paddingLeft: space.md },
  cancelLabel: { ...text.label, color: color.accent },

  scroll: { paddingBottom: space.xxxl, gap: space.md },

  totals: { gap: space.md },
  totalsHead: { flexDirection: 'row', alignItems: 'baseline', gap: space.xs },
  // `text.numeric` is sized for 14pt and carries `lineHeight: 20`. Raising
  // only the font size leaves the glyph taller than its own line box, which
  // clips the digits top and bottom and reads as bad spacing.
  totalsKcal: { ...text.numeric, fontSize: 32, lineHeight: 40 },
  totalsUnit: { ...text.bodyMuted },
  spacer: { flex: 1 },
  macros: { flexDirection: 'row', gap: space.sm },
  macro: { flex: 1, alignItems: 'center', paddingVertical: space.sm, borderRadius: radius.sm },
  macroValue: { ...text.label, fontSize: 14 },
  macroLabel: { ...text.overline, fontSize: 11, color: color.inkMuted },

  empty: { paddingVertical: space.xl },

  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  rowText: { flex: 1, gap: 2 },
  rowMeta: { ...text.bodyMuted, fontSize: 12 },
  rowStepper: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  stepButton: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
    backgroundColor: color.wash,
  },
  stepGlyph: { ...text.label, fontSize: 18, lineHeight: 20 },
  rowAmount: { ...text.numeric, fontSize: 14, minWidth: 52, textAlign: 'center' },
  remove: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  removeGlyph: { ...text.bodyMuted, fontSize: 20, lineHeight: 22 },

  error: { ...text.bodyMuted, color: color.dangerText, fontSize: 13 },
  hint: { ...text.bodyMuted, fontSize: 12, textAlign: 'center' },
});
