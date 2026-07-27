/**
 * Home — the CalDiet-style dashboard.
 *
 * Top to bottom: header with wordmark and streak flame, week strip, the calorie
 * ring card, three macro tiles with mini rings, and the day's logged food.
 * A floating black + button starts a log; it infers the meal slot from the time
 * of day, which the food screen lets the user override.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import {
  type DaySummary,
  type DiaryEntry,
  MEAL_LABELS,
  type MealSlot,
  deleteEntry,
  getDay,
  localDateString,
} from '@/api/diary';
import { getProgress } from '@/api/progress';
import { Card } from '@/components/card';
import { ProgressRing } from '@/components/progress-ring';
import { Screen } from '@/components/screen';
import { WeekStrip } from '@/components/week-strip';
import { HIT_SLOP_MIN, cardShadow, color, radius, space } from '@/theme/tokens';
import { fontFamily, text } from '@/theme/typography';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; summary: DaySummary }
  | { kind: 'error'; message: string };

/** Which meal the + button assumes, by hour. Overridable on the food screen. */
function slotForNow(): MealSlot {
  const hour = new Date().getHours();
  if (hour < 11) return 'breakfast';
  if (hour < 15) return 'lunch';
  if (hour < 18) return 'snack';
  return 'dinner';
}

export default function HomeScreen() {
  const router = useRouter();
  const [day, setDay] = useState(localDateString());
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [streak, setStreak] = useState<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;

      (async () => {
        try {
          const summary = await getDay(day);
          if (!cancelled) setState({ kind: 'ready', summary });
        } catch (caught) {
          if (cancelled) return;
          if (caught instanceof ApiError && caught.status === 404) {
            router.replace('/onboarding');
            return;
          }
          setState({
            kind: 'error',
            message:
              caught instanceof ApiError ? caught.userMessage : 'Could not load your day.',
          });
        }
      })();

      // The streak is decoration, not content: it renders whenever it arrives
      // and its failure must never block the dashboard.
      (async () => {
        try {
          const progress = await getProgress();
          if (!cancelled) setStreak(progress.streak_days);
        } catch {
          /* the flame simply doesn't render */
        }
      })();

      return () => {
        cancelled = true;
      };
    }, [day, router]),
  );

  function confirmDelete(entry: DiaryEntry) {
    Alert.alert('Delete entry?', `Remove ${entry.food_name}?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          void (async () => {
            try {
              await deleteEntry(entry.id);
              setState({ kind: 'ready', summary: await getDay(day) });
            } catch {
              Alert.alert('Could not delete that entry', 'Check your connection and try again.');
            }
          })();
        },
      },
    ]);
  }

  return (
    <Screen>
      {/* Header: wordmark + streak flame. */}
      <View style={styles.header}>
        <Text style={styles.wordmark}>CalAi</Text>
        <View style={styles.streakPill}>
          <Ionicons name="flame" size={16} color={color.flame} />
          <Text style={styles.streakCount}>{streak ?? '–'}</Text>
        </View>
      </View>

      <WeekStrip selected={day} onSelect={setDay} />

      {state.kind === 'loading' && (
        <View style={styles.centered}>
          <Text style={text.bodyMuted}>Loading…</Text>
        </View>
      )}

      {state.kind === 'error' && (
        <Card style={styles.errorCard}>
          <Text style={text.label}>Can&apos;t load your day</Text>
          <Text style={[text.bodyMuted, styles.errorBody]}>{state.message}</Text>
        </Card>
      )}

      {state.kind === 'ready' && <Dashboard summary={state.summary} onDelete={confirmDelete} />}

      {/* The floating log button — the app's most-used control, so it is the
          largest target on screen and never scrolls away. It now opens a choice
          of two ways to log, because photo and search are genuinely different
          starting points rather than one being a mode of the other. */}
      {menuOpen && (
        <Pressable
          onPress={() => setMenuOpen(false)}
          accessibilityLabel="Close menu"
          style={styles.scrim}
        />
      )}

      {menuOpen && (
        <View style={styles.menu}>
          <FabAction
            icon="camera"
            label="Scan a meal"
            onPress={() => {
              setMenuOpen(false);
              router.push({ pathname: '/scan', params: { day } });
            }}
          />
          <FabAction
            icon="search"
            label="Search food"
            onPress={() => {
              setMenuOpen(false);
              router.push({ pathname: '/search', params: { slot: slotForNow(), day } });
            }}
          />
        </View>
      )}

      <Pressable
        onPress={() => setMenuOpen((open) => !open)}
        accessibilityRole="button"
        accessibilityLabel={menuOpen ? 'Close log menu' : 'Log food'}
        accessibilityState={{ expanded: menuOpen }}
        style={({ pressed }) => [styles.fab, pressed && styles.fabPressed]}
      >
        <Ionicons name={menuOpen ? 'close' : 'add'} size={30} color={color.onDark} />
      </Pressable>
    </Screen>
  );
}

/** One row of the + menu: a readable label beside a round icon button. */
function FabAction({
  icon,
  label,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [styles.menuRow, pressed && styles.fabPressed]}
    >
      {/* The label is a tap target too, not just a caption — a bare icon here
          would make the user guess which circle is which. */}
      <View style={styles.menuLabelPill}>
        <Text style={styles.menuLabel}>{label}</Text>
      </View>
      <View style={styles.menuIcon}>
        <Ionicons name={icon} size={22} color={color.onDark} />
      </View>
    </Pressable>
  );
}

function Dashboard({
  summary,
  onDelete,
}: {
  summary: DaySummary;
  onDelete: (entry: DiaryEntry) => void;
}) {
  const eaten = summary.totals.kcal;
  const remaining = summary.remaining_calories;
  const over = remaining < 0;

  const entries = summary.meals
    .flatMap((meal) => meal.entries)
    .sort((a, b) => b.logged_at.localeCompare(a.logged_at));

  return (
    <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
      {/* The calorie ring card. */}
      <Card style={styles.calorieCard}>
        <View style={styles.calorieText}>
          <Text style={text.hero}>{Math.abs(Math.round(remaining)).toLocaleString()}</Text>
          <Text style={styles.calorieLabel}>
            {over ? 'Calories over' : 'Calories left'}
          </Text>
          <Text style={styles.calorieSub}>
            {Math.round(eaten).toLocaleString()} of {summary.target_calories.toLocaleString()} eaten
          </Text>
        </View>
        <ProgressRing
          progress={summary.target_calories > 0 ? eaten / summary.target_calories : 0}
          size={104}
          strokeWidth={10}
          tint={over ? color.danger : color.ink}
        >
          <Ionicons name="flame" size={26} color={over ? color.danger : color.ink} />
        </ProgressRing>
      </Card>

      {/* Macro tiles. "Left" mirrors the calorie card: this screen answers
          "what can I still eat", the Progress tab answers "what have I done". */}
      <View style={styles.macroRow}>
        <MacroTile
          label="Protein"
          eaten={summary.totals.protein_g}
          target={summary.target_macros.protein_g}
          tint={color.protein}
          icon="lightning-bolt"
        />
        <MacroTile
          label="Carbs"
          eaten={summary.totals.carbs_g}
          target={summary.target_macros.carbs_g}
          tint={color.carbs}
          icon="barley"
        />
        <MacroTile
          label="Fat"
          eaten={summary.totals.fat_g}
          target={summary.target_macros.fat_g}
          tint={color.fat}
          icon="water"
        />
      </View>

      <Text style={styles.sectionTitle}>Logged today</Text>

      {entries.length === 0 ? (
        <Card>
          <Text style={text.label}>Nothing logged yet</Text>
          <Text style={[text.bodyMuted, styles.emptyBody]}>
            Tap the + button to search a food and log your first meal of the day.
          </Text>
        </Card>
      ) : (
        entries.map((entry) => (
          <Pressable
            key={entry.id}
            onLongPress={() => onDelete(entry)}
            accessibilityRole="button"
            accessibilityHint="Long press to delete"
          >
            <Card style={styles.entryCard}>
              <View style={styles.entryText}>
                <Text style={text.label} numberOfLines={1}>
                  {entry.food_name}
                </Text>
                <Text style={styles.entryMeta}>
                  {MEAL_LABELS[entry.meal_slot]} ·{' '}
                  {entry.servings
                    ? `${entry.servings} serving${entry.servings === 1 ? '' : 's'}`
                    : `${Math.round(entry.quantity_grams)} g`}
                </Text>
                <View style={styles.chipRow}>
                  <MacroChip tint={color.protein} value={entry.protein_g} />
                  <MacroChip tint={color.carbs} value={entry.carbs_g} />
                  <MacroChip tint={color.fat} value={entry.fat_g} />
                </View>
              </View>
              <View style={styles.entryKcalBlock}>
                <Text style={text.heading}>{Math.round(entry.kcal)}</Text>
                <Text style={styles.entryKcalUnit}>kcal</Text>
              </View>
            </Card>
          </Pressable>
        ))
      )}

      {summary.totals.partial.length > 0 && (
        <Text style={styles.partialNote}>
          Some foods didn&apos;t report every nutrient, so some totals are minimums.
        </Text>
      )}
    </ScrollView>
  );
}

function MacroTile({
  label,
  eaten,
  target,
  tint,
  icon,
}: {
  label: string;
  eaten: number;
  target: number;
  tint: string;
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
}) {
  const left = Math.round(target - eaten);
  const over = left < 0;

  return (
    <Card compact style={styles.macroTile}>
      <Text style={styles.macroValue}>
        {Math.abs(left)}g
      </Text>
      <Text style={styles.macroLabel}>
        {label} {over ? 'over' : 'left'}
      </Text>
      <ProgressRing
        progress={target > 0 ? eaten / target : 0}
        size={44}
        strokeWidth={5}
        tint={tint}
      >
        <MaterialCommunityIcons name={icon} size={16} color={tint} />
      </ProgressRing>
    </Card>
  );
}

function MacroChip({ tint, value }: { tint: string; value: number }) {
  return (
    <View style={styles.chip}>
      <View style={[styles.chipDot, { backgroundColor: tint }]} />
      <Text style={styles.chipText}>{Math.round(value)}g</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: space.md,
  },
  wordmark: {
    fontFamily: fontFamily.extraBold,
    fontSize: 22,
    letterSpacing: -0.5,
    color: color.ink,
  },
  streakPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: color.surface,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    ...cardShadow,
  },
  streakCount: { ...text.numeric, fontSize: 15 },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll: { paddingTop: space.lg, paddingBottom: 96, gap: space.md },
  errorCard: { marginTop: space.lg },
  errorBody: { marginTop: space.xs },

  calorieCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: space.xl,
  },
  calorieText: { gap: 2, flexShrink: 1 },
  calorieLabel: { ...text.label, fontSize: 15 },
  calorieSub: { ...text.bodyMuted, fontSize: 13, marginTop: space.xs },

  macroRow: { flexDirection: 'row', gap: space.md },
  macroTile: { flex: 1, alignItems: 'flex-start', gap: space.xs },
  macroValue: { fontFamily: fontFamily.bold, fontSize: 18, color: color.ink },
  macroLabel: { ...text.bodyMuted, fontSize: 11, marginBottom: space.sm },

  sectionTitle: { ...text.heading, marginTop: space.md },

  entryCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
  },
  entryText: { flex: 1, gap: 3 },
  entryMeta: { ...text.bodyMuted, fontSize: 12 },
  chipRow: { flexDirection: 'row', gap: space.sm, marginTop: space.xs },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  chipDot: { width: 7, height: 7, borderRadius: radius.pill },
  chipText: { ...text.numeric, fontSize: 12, color: color.inkMuted },
  entryKcalBlock: { alignItems: 'flex-end' },
  entryKcalUnit: { ...text.bodyMuted, fontSize: 11 },

  emptyBody: { marginTop: space.xs, fontSize: 13 },
  partialNote: { ...text.bodyMuted, fontSize: 12, marginTop: space.sm },

  // Covers the whole screen so a tap anywhere dismisses the menu. Barely tinted:
  // enough to signal "this is modal", not enough to hide the day underneath.
  scrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(23, 24, 26, 0.18)',
  },
  menu: {
    position: 'absolute',
    right: space.xl,
    bottom: space.xl + 60 + space.md,
    alignItems: 'flex-end',
    gap: space.md,
  },
  menuRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  menuLabelPill: {
    backgroundColor: color.surface,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    ...cardShadow,
    elevation: 4,
  },
  menuLabel: { ...text.label, fontSize: 14 },
  menuIcon: {
    width: 48,
    height: 48,
    borderRadius: radius.pill,
    backgroundColor: color.ink,
    alignItems: 'center',
    justifyContent: 'center',
    ...cardShadow,
    elevation: 4,
  },

  fab: {
    position: 'absolute',
    right: space.xl,
    bottom: space.xl,
    width: 60,
    height: 60,
    borderRadius: radius.pill,
    backgroundColor: color.ink,
    alignItems: 'center',
    justifyContent: 'center',
    ...cardShadow,
    // The shadow token is tuned for cards; a floating button needs more depth
    // to read as floating.
    elevation: 6,
    minWidth: HIT_SLOP_MIN,
    minHeight: HIT_SLOP_MIN,
  },
  fabPressed: { opacity: 0.85 },
});
