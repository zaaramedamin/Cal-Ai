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
import { ApiError } from '@/api/client';
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
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function MealBuilderScreen() {
  const router = useRouter();
  const draft = useDraftMeal();
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
      setError(caught instanceof ApiError ? caught.userMessage : 'Could not save that meal.');
      setSaving(false);
    }
  };

  const discard = () => {
    if (draft.items.length === 0 && !draft.name) {
      router.back();
      return;
    }
    Alert.alert('Discard this meal?', 'Nothing will be saved.', [
      { text: 'Keep editing', style: 'cancel' },
      {
        text: 'Discard',
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
        <Text style={text.overline}>{editing ? 'Edit meal' : 'New meal'}</Text>
        <Pressable onPress={discard} accessibilityRole="button" style={styles.cancel}>
          <Text style={styles.cancelLabel}>Cancel</Text>
        </Pressable>
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        <TextField
          label="Name"
          value={draft.name}
          onChangeText={draftActions.setName}
          placeholder="Breakfast, usual lunch…"
          maxLength={80}
        />

        <Card style={styles.totals}>
          <View style={styles.totalsHead}>
            <Text style={styles.totalsKcal}>{Math.round(totals.kcal)}</Text>
            <Text style={styles.totalsUnit}>kcal</Text>
            <View style={styles.spacer} />
            <Text style={text.bodyMuted}>{Math.round(totals.grams)} g total</Text>
          </View>
          <View style={styles.macros}>
            <Macro label="Protein" value={totals.protein_g} tint={color.proteinTint} />
            <Macro label="Carbs" value={totals.carbs_g} tint={color.carbsTint} />
            <Macro label="Fat" value={totals.fat_g} tint={color.fatTint} />
          </View>
        </Card>

        {draft.items.length === 0 ? (
          <View style={styles.empty}>
            <Text style={text.bodyMuted}>
              No ingredients yet. Add the things you put on the plate — the amounts stay in each
              food&apos;s own unit.
            </Text>
          </View>
        ) : (
          draft.items.map((item) => <IngredientRow key={item.slug} item={item} />)
        )}

        <Button
          label="Add ingredient"
          variant="secondary"
          onPress={() => router.push({ pathname: '/catalogue', params: { mode: 'meal' } })}
        />

        {error && (
          <Text style={styles.error} accessibilityRole="alert">
            {error}
          </Text>
        )}

        <Button
          label={editing ? 'Save changes' : 'Save meal'}
          onPress={() => void save()}
          disabled={!canSave}
          loading={saving}
        />

        {!canSave && draft.items.length > 0 && (
          <Text style={styles.hint}>Give the meal a name to save it.</Text>
        )}
      </ScrollView>
    </Screen>
  );
}

function IngredientRow({ item }: { item: DraftMealItem }) {
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
          {item.nameEn}
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
          accessibilityLabel={`Less ${item.nameEn}`}
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
          accessibilityLabel={`More ${item.nameEn}`}
          style={styles.stepButton}
        >
          <Text style={styles.stepGlyph}>+</Text>
        </Pressable>
      </View>

      <PressableScale
        onPress={() => draftActions.removeItem(item.slug)}
        accessibilityRole="button"
        accessibilityLabel={`Remove ${item.nameEn}`}
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
  totalsKcal: { ...text.numeric, fontSize: 32 },
  totalsUnit: { ...text.bodyMuted },
  spacer: { flex: 1 },
  macros: { flexDirection: 'row', gap: space.sm },
  macro: { flex: 1, alignItems: 'center', paddingVertical: space.sm, borderRadius: radius.sm },
  macroValue: { ...text.label, fontSize: 14 },
  macroLabel: { ...text.overline, fontSize: 9, color: color.inkMuted },

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

  error: { ...text.bodyMuted, color: color.danger, fontSize: 13 },
  hint: { ...text.bodyMuted, fontSize: 12, textAlign: 'center' },
});
