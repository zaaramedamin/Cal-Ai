/**
 * The diary — the screen this app exists for.
 *
 * Logging food is the action performed five or more times a day, so the path to
 * it is kept as short as possible: every meal section has its own add button
 * that carries the slot with it, meaning "add lunch" is one tap from here rather
 * than a search followed by choosing where it goes.
 */

import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import {
  type DaySummary,
  type DiaryEntry,
  MEAL_LABELS,
  type MealSlot,
  addDays,
  deleteEntry,
  getDay,
  localDateString,
} from '@/api/diary';
import { MacroBar } from '@/components/macro-bar';
import { Screen } from '@/components/screen';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function DiaryScreen() {
  const router = useRouter();
  const [day, setDay] = useState(localDateString());
  const [summary, setSummary] = useState<DaySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (target: string) => {
    try {
      setSummary(await getDay(target));
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        setError('Complete onboarding first to see your targets.');
        return;
      }
      setError(caught instanceof ApiError ? caught.userMessage : 'Could not load your diary.');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load(day);
    }, [day, load]),
  );

  async function handleDelete(entry: DiaryEntry) {
    // Confirm first: deleting is destructive and a mis-tap in a dense list is
    // easy. An undo would be better than a dialog, but undo needs state this
    // screen does not have yet — noted for Phase 6.
    Alert.alert('Delete entry?', `Remove ${entry.food_name} from ${MEAL_LABELS[entry.meal_slot]}?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          void (async () => {
            try {
              await deleteEntry(entry.id);
              await load(day);
            } catch {
              Alert.alert('Could not delete that entry', 'Check your connection and try again.');
            }
          })();
        },
      },
    ]);
  }

  const isToday = day === localDateString();

  return (
    <Screen>
      <View style={styles.dateBar}>
        <DateButton label="‹" onPress={() => setDay(addDays(day, -1))} hint="Previous day" />
        <Pressable onPress={() => setDay(localDateString())} style={styles.dateLabel}>
          <Text style={text.label}>{isToday ? 'Today' : formatDay(day)}</Text>
          {!isToday && <Text style={styles.backToToday}>Tap for today</Text>}
        </Pressable>
        <DateButton
          label="›"
          onPress={() => setDay(addDays(day, 1))}
          hint="Next day"
          disabled={isToday}
        />
      </View>

      {error && (
        <View style={styles.callout} accessibilityRole="alert">
          <Text style={styles.calloutText}>{error}</Text>
        </View>
      )}

      {!error && summary === null && (
        <View style={styles.centered}>
          <Text style={text.bodyMuted}>Loading…</Text>
        </View>
      )}

      {summary && (
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <Text style={text.overline}>
            {summary.remaining_calories >= 0 ? 'Remaining' : 'Over by'}
          </Text>
          <View style={styles.heroBlock}>
            <Text style={text.hero}>{Math.abs(summary.remaining_calories).toLocaleString()}</Text>
            <Text style={text.overline}>
              kcal · {Math.round(summary.totals.kcal).toLocaleString()} of{' '}
              {summary.target_calories.toLocaleString()}
            </Text>
          </View>

          {/* The signature mark, at hero scale, showing what the day is made of.
              The tick marks where the target sits. */}
          <MacroBar
            macros={summary.totals}
            scale="hero"
            showLegend
            targetCalories={summary.target_calories}
          />

          <View style={styles.targetRow}>
            <TargetChip label="P" eaten={summary.totals.protein_g} target={summary.target_macros.protein_g} />
            <TargetChip label="C" eaten={summary.totals.carbs_g} target={summary.target_macros.carbs_g} />
            <TargetChip label="F" eaten={summary.totals.fat_g} target={summary.target_macros.fat_g} />
          </View>

          {summary.meals.map((meal) => (
            <View key={meal.meal_slot} style={styles.meal}>
              <View style={styles.mealHeader}>
                <Text style={text.heading}>{MEAL_LABELS[meal.meal_slot]}</Text>
                <Text style={styles.mealKcal}>
                  {Math.round(meal.totals.kcal).toLocaleString()} kcal
                </Text>
              </View>

              {meal.entries.length === 0 ? (
                <Text style={styles.emptyMeal}>Nothing logged yet.</Text>
              ) : (
                meal.entries.map((entry) => (
                  <Pressable
                    key={entry.id}
                    onLongPress={() => void handleDelete(entry)}
                    accessibilityRole="button"
                    accessibilityHint="Long press to delete"
                    style={styles.entry}
                  >
                    <View style={styles.entryText}>
                      <Text style={text.label} numberOfLines={1}>
                        {entry.food_name}
                      </Text>
                      <Text style={styles.entryMeta}>
                        {Math.round(entry.quantity_grams)} g
                        {entry.food_brand ? ` · ${entry.food_brand}` : ''}
                      </Text>
                      <View style={styles.entryBar}>
                        <MacroBar macros={entry} scale="row" />
                      </View>
                    </View>
                    <Text style={styles.entryKcal}>{Math.round(entry.kcal)}</Text>
                  </Pressable>
                ))
              )}

              <Pressable
                onPress={() =>
                  router.push({ pathname: '/search', params: { slot: meal.meal_slot, day } })
                }
                accessibilityRole="button"
                style={styles.addButton}
              >
                <Text style={styles.addLabel}>+ Add to {MEAL_LABELS[meal.meal_slot]}</Text>
              </Pressable>
            </View>
          ))}

          {summary.totals.partial.length > 0 && (
            <Text style={styles.partialNote}>
              Some foods today didn&apos;t report {formatPartial(summary.totals.partial)}, so
              those totals are a minimum rather than a complete figure.
            </Text>
          )}
        </ScrollView>
      )}
    </Screen>
  );
}

function TargetChip({ label, eaten, target }: { label: string; eaten: number; target: number }) {
  return (
    <View style={styles.chip}>
      <Text style={text.overline}>{label}</Text>
      <Text style={styles.chipValue}>
        {Math.round(eaten)}
        <Text style={styles.chipTarget}> / {target} g</Text>
      </Text>
    </View>
  );
}

function DateButton({
  label,
  onPress,
  hint,
  disabled,
}: {
  label: string;
  onPress: () => void;
  hint: string;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={hint}
      style={[styles.dateButton, disabled && styles.dateButtonDisabled]}
    >
      <Text style={styles.dateButtonLabel}>{label}</Text>
    </Pressable>
  );
}

function formatDay(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

const NUTRIENT_NAMES: Record<string, string> = {
  sugars_g: 'sugars',
  saturated_fat_g: 'saturates',
  fibre_g: 'fibre',
  sodium_mg: 'sodium',
};

function formatPartial(fields: string[]): string {
  const names = fields.map((field) => NUTRIENT_NAMES[field] ?? field);
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(', ')} or ${names[names.length - 1]}`;
}

const styles = StyleSheet.create({
  content: { paddingBottom: space.xxl },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  dateBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.lg,
  },
  dateButton: {
    width: HIT_SLOP_MIN,
    height: HIT_SLOP_MIN,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    backgroundColor: color.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.hairline,
  },
  dateButtonDisabled: { opacity: 0.35 },
  dateButtonLabel: { ...text.heading, lineHeight: 24 },
  dateLabel: { alignItems: 'center' },
  backToToday: { ...text.bodyMuted, fontSize: 11 },
  heroBlock: { marginTop: space.xs, marginBottom: space.lg },
  targetRow: { flexDirection: 'row', gap: space.sm, marginTop: space.lg },
  chip: {
    flex: 1,
    padding: space.sm,
    backgroundColor: color.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.hairline,
    borderRadius: radius.md,
    gap: 2,
  },
  chipValue: { ...text.numeric },
  chipTarget: { ...text.bodyMuted, fontSize: 12 },
  meal: { marginTop: space.xl },
  mealHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: space.sm,
  },
  mealKcal: { ...text.numeric, color: color.inkMuted },
  emptyMeal: { ...text.bodyMuted, fontSize: 13, paddingVertical: space.sm },
  entry: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.hairline,
  },
  entryText: { flex: 1, gap: 3 },
  entryMeta: { ...text.bodyMuted, fontSize: 12 },
  entryBar: { marginTop: space.xs },
  entryKcal: { ...text.numeric },
  addButton: { paddingVertical: space.md, minHeight: HIT_SLOP_MIN, justifyContent: 'center' },
  addLabel: { ...text.label, color: color.clay },
  callout: {
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.clay,
  },
  calloutText: { ...text.body, fontSize: 14 },
  partialNote: {
    ...text.bodyMuted,
    fontSize: 12,
    lineHeight: 17,
    marginTop: space.xl,
  },
});
