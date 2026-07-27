/**
 * Food detail and portion selector.
 *
 * The last screen before something lands in the diary, so it has to make the
 * quantity unambiguous. Portions are offered as chips with their gram weight
 * shown — "1 medium (118 g)" — because the label alone hides the number the
 * calculation actually uses, and a user who thinks a medium banana is 150 g
 * should be able to see the difference rather than discover it later.
 */

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import {
  type Food,
  MEAL_LABELS,
  type MealSlot,
  getFood,
  logFood,
} from '@/api/diary';
import { Button } from '@/components/button';
import { MacroBar } from '@/components/macro-bar';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { HOME } from '@/routes';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function FoodDetailScreen() {
  const router = useRouter();
  const { id, slot, day } = useLocalSearchParams<{
    id: string;
    slot?: MealSlot;
    day?: string;
  }>();

  const [food, setFood] = useState<Food | null>(null);
  const [grams, setGrams] = useState('100');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // The + button infers a slot from the time of day; this is where the user
  // corrects it. State starts from the param and the chips below override.
  const [chosenSlot, setChosenSlot] = useState<MealSlot>(slot ?? 'snack');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await getFood(id);
        if (cancelled) return;
        setFood(loaded);
        // Start at the food's default portion when it has one; 100 g otherwise.
        const preferred = loaded.portions.find((portion) => portion.is_default);
        if (preferred) setGrams(String(Math.round(preferred.grams)));
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.userMessage : 'Could not load this food.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const quantity = Number(grams);
  const valid = Number.isFinite(quantity) && quantity > 0;

  // Scaled live from the per-100 g values, so the numbers on screen are always
  // the numbers that will be logged.
  const scaled = useMemo(() => {
    if (!food || !valid) return null;
    const factor = quantity / 100;
    return {
      kcal: food.kcal * factor,
      protein_g: food.protein_g * factor,
      carbs_g: food.carbs_g * factor,
      fat_g: food.fat_g * factor,
      fibre_g: food.fibre_g === null ? null : food.fibre_g * factor,
      sugars_g: food.sugars_g === null ? null : food.sugars_g * factor,
      saturated_fat_g:
        food.saturated_fat_g === null ? null : food.saturated_fat_g * factor,
      sodium_mg: food.sodium_mg === null ? null : food.sodium_mg * factor,
    };
  }, [food, quantity, valid]);

  async function handleLog() {
    if (!valid || !food) return;
    setSaving(true);
    setError(null);
    try {
      await logFood({
        foodId: food.id,
        mealSlot: chosenSlot,
        quantityGrams: quantity,
        localDate: day || undefined,
      });
      // Back to the dashboard, which refetches on focus. dismissAll rather than
      // back, so the search screen is not left behind on the stack.
      router.dismissAll();
      router.replace(HOME);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.userMessage : 'Could not log this food.');
    } finally {
      setSaving(false);
    }
  }

  if (error && !food) {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={text.title}>Couldn&apos;t load this food</Text>
          <Text style={[text.bodyMuted, styles.errorBody]}>{error}</Text>
          <Button label="Go back" onPress={() => router.back()} />
        </View>
      </Screen>
    );
  }

  if (!food || !scaled) {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={text.bodyMuted}>Loading…</Text>
        </View>
      </Screen>
    );
  }

  const unit = food.is_liquid ? 'ml' : 'g';

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={text.overline}>Add to {MEAL_LABELS[chosenSlot]}</Text>
        <Text style={text.title}>{food.name}</Text>
        {food.brand && <Text style={[text.bodyMuted, styles.brand]}>{food.brand}</Text>}

        <View style={styles.heroBlock}>
          <Text style={text.hero}>{Math.round(scaled.kcal).toLocaleString()}</Text>
          <Text style={text.overline}>
            kcal for {quantity} {unit}
          </Text>
        </View>

        <MacroBar macros={scaled} scale="hero" showLegend />

        <Text style={[text.overline, styles.sectionLabel]}>Meal</Text>
        <View style={styles.slotRow}>
          {(Object.keys(MEAL_LABELS) as MealSlot[]).map((option) => {
            const selected = option === chosenSlot;
            return (
              <Pressable
                key={option}
                onPress={() => setChosenSlot(option)}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                style={[styles.slotChip, selected && styles.slotChipSelected]}
              >
                <Text style={[styles.slotChipLabel, selected && styles.slotChipLabelSelected]}>
                  {MEAL_LABELS[option]}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Text style={[text.overline, styles.sectionLabel]}>Quantity</Text>
        <TextField
          label={`Amount in ${unit}`}
          value={grams}
          onChangeText={setGrams}
          keyboardType="decimal-pad"
          error={valid ? null : 'Enter an amount greater than zero.'}
        />

        {food.portions.length > 0 && (
          <View style={styles.portions}>
            {food.portions.map((portion) => {
              const selected = Math.round(portion.grams) === Math.round(quantity);
              return (
                <Pressable
                  key={portion.id}
                  onPress={() => setGrams(String(Math.round(portion.grams)))}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  style={[styles.portion, selected && styles.portionSelected]}
                >
                  <Text style={[text.label, styles.portionLabel]}>{portion.label}</Text>
                  <Text style={styles.portionGrams}>
                    {Math.round(portion.grams)} {unit}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        )}

        <Text style={[text.overline, styles.sectionLabel]}>Full nutrition</Text>
        <View style={styles.table}>
          <NutrientRow label="Protein" value={scaled.protein_g} unit="g" />
          <NutrientRow label="Carbohydrate" value={scaled.carbs_g} unit="g" />
          <NutrientRow label="of which sugars" value={scaled.sugars_g} unit="g" indented />
          <NutrientRow label="Fat" value={scaled.fat_g} unit="g" />
          <NutrientRow
            label="of which saturates"
            value={scaled.saturated_fat_g}
            unit="g"
            indented
          />
          <NutrientRow label="Fibre" value={scaled.fibre_g} unit="g" />
          <NutrientRow label="Sodium" value={scaled.sodium_mg} unit="mg" />
        </View>

        <Text style={styles.source}>
          Source: {food.source === 'usda' ? 'USDA FoodData Central' : food.source} ·{' '}
          {food.source_id}
        </Text>

        {error && (
          <View style={styles.callout} accessibilityRole="alert">
            <Text style={styles.calloutText}>{error}</Text>
          </View>
        )}

        <View style={styles.actions}>
          <Button
            label={`Log ${quantity || 0} ${unit}`}
            disabled={!valid}
            loading={saving}
            onPress={() => void handleLog()}
          />
        </View>
      </ScrollView>
    </Screen>
  );
}

function NutrientRow({
  label,
  value,
  unit,
  indented,
}: {
  label: string;
  value: number | null;
  unit: string;
  indented?: boolean;
}) {
  return (
    <View style={styles.tableRow}>
      <Text style={[styles.tableLabel, indented && styles.tableLabelIndented]}>{label}</Text>
      {/* An em dash, never 0. Null means this source did not report the
          nutrient, which is a different claim from "there is none of it". */}
      <Text style={styles.tableValue}>
        {value === null ? '—' : `${value.toFixed(1)} ${unit}`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: space.xxl },
  centered: { flex: 1, justifyContent: 'center', gap: space.md },
  errorBody: { marginBottom: space.lg },
  brand: { marginTop: space.xs },
  heroBlock: { marginTop: space.lg, marginBottom: space.lg },
  sectionLabel: { marginTop: space.xl, marginBottom: space.sm },
  slotRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  slotChip: {
    minHeight: HIT_SLOP_MIN - 8,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
  },
  slotChipSelected: { backgroundColor: color.accent, borderColor: color.accent },
  slotChipLabel: { ...text.label, fontSize: 13 },
  slotChipLabelSelected: { color: color.onDark },
  portions: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md },
  portion: {
    minHeight: HIT_SLOP_MIN,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.md,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
  },
  portionSelected: { borderColor: color.accent, backgroundColor: color.accentTint },
  portionLabel: { fontSize: 13 },
  portionGrams: { ...text.bodyMuted, fontSize: 11 },
  table: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.hairline,
    paddingHorizontal: space.lg,
  },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.hairline,
  },
  tableLabel: { ...text.body, fontSize: 14 },
  tableLabelIndented: { paddingLeft: space.md, color: color.inkMuted, fontSize: 13 },
  tableValue: { ...text.numeric, fontSize: 14 },
  source: { ...text.bodyMuted, fontSize: 11, marginTop: space.md },
  callout: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.clayDeep,
  },
  calloutText: { ...text.body, fontSize: 14 },
  actions: { marginTop: space.xl },
});
