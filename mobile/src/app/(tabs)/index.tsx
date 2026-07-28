/**
 * Home — the dashboard.
 *
 * Top to bottom: greeting and streak, week strip, the calorie ring, three macro
 * tiles on tinted surfaces, quick-add chips, then the day's food.
 *
 * **Quick-add is the most important thing on this screen after the ring.** The
 * commonest act in a food tracker is repeating yesterday, and without these
 * chips that act costs six taps: open search, type, wait, choose, set the
 * amount, confirm. Each chip carries the food *and* the amount last used, so it
 * costs one. Everything else here is reporting; this is the only part that
 * saves time.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';

import { ApiError } from '@/api/client';
import {
  type DaySummary,
  type DiaryEntry,
  type MealSlot,
  type QuickAddFood,
  deleteEntry,
  getDay,
  getQuickAdd,
  localDateString,
  logFood,
} from '@/api/diary';
import { type ProfileWithTargets, getProfile } from '@/api/profile';
import { getProgress } from '@/api/progress';
import { type Suggestion, getSuggestions } from '@/api/suggestions';
import { BodyCard } from '@/components/body-avatar';
import { Card } from '@/components/card';
import { CountUp, EnterUp, GrowBar, PressableScale } from '@/components/motion';
import { ProgressRing } from '@/components/progress-ring';
import { Screen } from '@/components/screen';
import { WeekStrip } from '@/components/week-strip';
import { Wordmark } from '@/components/wordmark';
import { type Translate, useT } from '@/i18n';
import { photo } from '@/theme/imagery';
import { HIT_SLOP_MIN, color, elevation, radius, space } from '@/theme/tokens';
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

function greeting(t: Translate): string {
  const hour = new Date().getHours();
  if (hour < 12) return t('home.goodMorning');
  if (hour < 18) return t('home.goodAfternoon');
  return t('home.goodEvening');
}

export default function HomeScreen() {
  const router = useRouter();
  const t = useT();
  const [day, setDay] = useState(localDateString());
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [streak, setStreak] = useState<number | null>(null);
  const [quickAdd, setQuickAdd] = useState<QuickAddFood[]>([]);
  const [addingId, setAddingId] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggestionNote, setSuggestionNote] = useState<string | null>(null);
  const [body, setBody] = useState<ProfileWithTargets | null>(null);

  const reload = useCallback(async () => {
    setState({ kind: 'ready', summary: await getDay(day) });
  }, [day]);

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

      // Streak and quick-add are both decoration in the strict sense: the screen
      // is complete without them, so neither failure may block the day loading.
      (async () => {
        try {
          const progress = await getProgress();
          if (!cancelled) setStreak(progress.streak_days);
        } catch {
          /* the flame simply doesn't render */
        }
      })();

      (async () => {
        try {
          const foods = await getQuickAdd();
          if (!cancelled) setQuickAdd(foods);
        } catch {
          /* the chips simply don't render */
        }
      })();

      (async () => {
        try {
          const profile = await getProfile();
          if (!cancelled) setBody(profile);
        } catch {
          /* the figure simply doesn't render */
        }
      })();

      (async () => {
        try {
          const response = await getSuggestions();
          if (cancelled) return;
          setSuggestions(response.suggestions);
          setSuggestionNote(response.note);
        } catch {
          /* the card simply doesn't render */
        }
      })();

      return () => {
        cancelled = true;
      };
    }, [day, router]),
  );

  async function handleQuickAdd(food: QuickAddFood) {
    setAddingId(food.id);
    try {
      await logFood({
        foodId: food.id,
        // The slot comes from the clock, not from last time: porridge logged as
        // breakfast yesterday is still breakfast today, but a snack eaten at
        // 8pm last week should not be filed as a snack at 8am.
        mealSlot: slotForNow(),
        quantityGrams: food.last_quantity_grams,
        localDate: day,
      });
      await reload();
      // Both refreshed after logging: the ranking may have changed, and the
      // remaining budget certainly has, which is what suggestions are ranked on.
      setQuickAdd(await getQuickAdd());
      const next = await getSuggestions();
      setSuggestions(next.suggestions);
      setSuggestionNote(next.note);
    } catch (caught) {
      Alert.alert(
        'Could not log that',
        caught instanceof ApiError ? caught.userMessage : 'Check your connection and try again.',
      );
    } finally {
      setAddingId(null);
    }
  }

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
              await reload();
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
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>{greeting(t)}</Text>
          <Wordmark size={24} />
        </View>
        {streak !== null && streak > 0 && (
          <Animated.View entering={FadeIn.duration(300)} style={styles.streakPill}>
            <Ionicons name="flame" size={16} color={color.flame} />
            <Text style={styles.streakCount}>{streak}</Text>
          </Animated.View>
        )}
      </View>

      <WeekStrip selected={day} onSelect={setDay} />

      {state.kind === 'loading' && (
        <View style={styles.centered}>
          <Text style={text.bodyMuted}>Loading…</Text>
        </View>
      )}

      {state.kind === 'error' && (
        <Card style={styles.errorCard}>
          <Text style={text.label}>{t('home.cantLoadDay')}</Text>
          <Text style={[text.bodyMuted, styles.errorBody]}>{state.message}</Text>
        </Card>
      )}

      {state.kind === 'ready' && (
        <Dashboard
          summary={state.summary}
          body={body}
          quickAdd={quickAdd}
          suggestions={suggestions}
          suggestionNote={suggestionNote}
          addingId={addingId}
          onQuickAdd={(food) => void handleQuickAdd(food)}
          onDelete={confirmDelete}
        />
      )}

      {menuOpen && (
        <Animated.View entering={FadeIn.duration(150)} exiting={FadeOut.duration(120)}>
          <Pressable
            onPress={() => setMenuOpen(false)}
            accessibilityLabel="Close menu"
            style={styles.scrim}
          />
        </Animated.View>
      )}

      {menuOpen && (
        <Animated.View
          entering={FadeIn.duration(160)}
          exiting={FadeOut.duration(120)}
          style={styles.menu}
        >
          <FabAction
            icon="camera"
            label={t('home.scanMeal')}
            onPress={() => {
              setMenuOpen(false);
              router.push({ pathname: '/scan', params: { day } });
            }}
          />
          {/* Ordered above search on purpose. The catalogue is the path that
              works for someone who does not already know what USDA calls their
              food, which is most people most of the time; search is the escape
              hatch for the thing the catalogue does not carry. */}
          <FabAction
            icon="restaurant"
            label={t('home.myMeals')}
            onPress={() => {
              setMenuOpen(false);
              router.push('/meals');
            }}
          />
          <FabAction
            icon="nutrition"
            label={t('home.ingredients')}
            onPress={() => {
              setMenuOpen(false);
              router.push({ pathname: '/catalogue', params: { slot: slotForNow(), day } });
            }}
          />
          <FabAction
            icon="search"
            label={t('home.searchFood')}
            onPress={() => {
              setMenuOpen(false);
              router.push({ pathname: '/search', params: { slot: slotForNow(), day } });
            }}
          />
        </Animated.View>
      )}

      <PressableScale
        onPress={() => setMenuOpen((open) => !open)}
        accessibilityRole="button"
        accessibilityLabel={menuOpen ? 'Close log menu' : 'Log food'}
        accessibilityState={{ expanded: menuOpen }}
        style={styles.fab}
        scaleTo={0.92}
      >
        <Ionicons name={menuOpen ? 'close' : 'add'} size={30} color={color.onDark} />
      </PressableScale>
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
    <PressableScale
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={styles.menuRow}
    >
      {/* The label is a tap target too, not just a caption — a bare icon here
          would make the user guess which circle is which. */}
      <View style={styles.menuLabelPill}>
        <Text style={styles.menuLabel}>{label}</Text>
      </View>
      <View style={styles.menuIcon}>
        <Ionicons name={icon} size={22} color={color.onDark} />
      </View>
    </PressableScale>
  );
}

function Dashboard({
  summary,
  body,
  quickAdd,
  suggestions,
  suggestionNote,
  addingId,
  onQuickAdd,
  onDelete,
}: {
  summary: DaySummary;
  /** Null while the profile is loading, or if it failed — the figure is
      decoration in the strict sense and must never block the day. */
  body: ProfileWithTargets | null;
  quickAdd: QuickAddFood[];
  suggestions: Suggestion[];
  suggestionNote: string | null;
  addingId: string | null;
  onQuickAdd: (food: QuickAddFood) => void;
  onDelete: (entry: DiaryEntry) => void;
}) {
  const router = useRouter();
  const t = useT();
  const eaten = summary.totals.kcal;
  const remaining = summary.remaining_calories;
  const over = remaining < 0;

  const entries = summary.meals
    .flatMap((meal) => meal.entries)
    .sort((a, b) => b.logged_at.localeCompare(a.logged_at));

  return (
    <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
      <EnterUp index={0}>
        <Card style={styles.calorieCard}>
          <View style={styles.calorieText}>
            <CountUp value={Math.abs(Math.round(remaining))} style={styles.calorieValue} />
            <Text style={styles.calorieLabel}>
              {over ? t('home.caloriesOver') : t('home.caloriesLeft')}
            </Text>
            <Text style={styles.calorieSub}>
              {t('home.eatenOf', {
                eaten: Math.round(eaten).toLocaleString(),
                target: summary.target_calories.toLocaleString(),
              })}
            </Text>
          </View>
          <ProgressRing
            progress={summary.target_calories > 0 ? eaten / summary.target_calories : 0}
            size={112}
            strokeWidth={11}
            tint={over ? color.warning : color.accent}
          >
            <Ionicons name="flame" size={26} color={over ? color.warning : color.accent} />
          </ProgressRing>
        </Card>
      </EnterUp>

      {/* Macro tiles. "Left" mirrors the calorie card: this screen answers
          "what can I still eat", the Progress tab answers "what have I done". */}
      <EnterUp index={1}>
        <View style={styles.macroRow}>
          <MacroTile
            label={t('common.protein')}
            eaten={summary.totals.protein_g}
            target={summary.target_macros.protein_g}
            tint={color.protein}
            surface={color.proteinTint}
            icon="lightning-bolt"
          />
          <MacroTile
            label={t('common.carbs')}
            eaten={summary.totals.carbs_g}
            target={summary.target_macros.carbs_g}
            tint={color.carbs}
            surface={color.carbsTint}
            icon="barley"
          />
          <MacroTile
            label={t('common.fat')}
            eaten={summary.totals.fat_g}
            target={summary.target_macros.fat_g}
            tint={color.fat}
            surface={color.fatTint}
            icon="water"
          />
        </View>
      </EnterUp>

      {/* Below the ring and the macros on purpose. Those answer "what can I eat
          now", which is why someone opened the app; this answers "where am I",
          which is a slower question and does not belong above the fast one. */}
      {body && (
        <EnterUp index={2}>
          <BodyCard
            heightCm={body.profile.height_cm}
            weightKg={body.current_weight_kg}
            targetKg={body.profile.target_weight_kg}
          />
        </EnterUp>
      )}

      {quickAdd.length > 0 && (
        <EnterUp index={3}>
          <View style={styles.quickAddBlock}>
            <Text style={styles.sectionTitle}>{t('home.yourUsuals')}</Text>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.chipRail}
            >
              {quickAdd.map((food) => (
                <QuickAddChip
                  key={food.id}
                  food={food}
                  busy={addingId === food.id}
                  onPress={() => onQuickAdd(food)}
                />
              ))}
            </ScrollView>
          </View>
        </EnterUp>
      )}

      {(suggestions.length > 0 || suggestionNote) && (
        <EnterUp index={3}>
          <Card style={styles.suggestCard}>
            <View style={styles.suggestHead}>
              <View style={styles.suggestIcon}>
                <Ionicons name="bulb-outline" size={16} color={color.accent} />
              </View>
              <Text style={text.heading}>{t('home.whatToEat')}</Text>
            </View>

            {suggestions.length === 0 ? (
              <Text style={styles.suggestNote}>{suggestionNote}</Text>
            ) : (
              suggestions.map((suggestion) => (
                <PressableScale
                  key={suggestion.food.id}
                  onPress={() =>
                    router.push({
                      pathname: '/food/[id]',
                      params: { id: suggestion.food.id, slot: slotForNow() },
                    })
                  }
                  accessibilityRole="button"
                  accessibilityLabel={`${suggestion.food.name}, ${Math.round(
                    suggestion.grams,
                  )} grams`}
                  style={styles.suggestRow}
                  scaleTo={0.985}
                >
                  <View style={styles.suggestText}>
                    <Text style={text.label} numberOfLines={1}>
                      {suggestion.food.name}
                    </Text>
                    {/* The reason is the point. A recommendation with no stated
                        reason is indistinguishable from an advertisement. */}
                    <Text style={styles.suggestReason} numberOfLines={2}>
                      {suggestion.reason}
                    </Text>
                  </View>
                  <View style={styles.suggestAmount}>
                    <Text style={styles.suggestGrams}>{Math.round(suggestion.grams)} g</Text>
                    <Text style={styles.suggestKcal}>{Math.round(suggestion.kcal)} kcal</Text>
                  </View>
                </PressableScale>
              ))
            )}
          </Card>
        </EnterUp>
      )}

      <Text style={styles.sectionTitle}>{t('home.loggedToday')}</Text>

      {entries.length === 0 ? (
        <EnterUp index={4}>
          <Card style={styles.emptyCard}>
            {/* Renders only when the photo exists; the card is designed to look
                complete without it, so a fresh clone is never half-drawn. */}
            {photo('emptyDiary') && (
              <Image source={photo('emptyDiary')!} style={styles.emptyPhoto} resizeMode="cover" />
            )}
            <Text style={text.label}>Nothing logged yet</Text>
            <Text style={[text.bodyMuted, styles.emptyBody]}>
              {quickAdd.length > 0
                ? 'Tap one of your usuals above, or use + to scan a meal.'
                : 'Tap + to photograph a meal or search for a food.'}
            </Text>
          </Card>
        </EnterUp>
      ) : (
        entries.map((entry, index) => (
          <EnterUp key={entry.id} index={4 + index}>
            <PressableScale
              onLongPress={() => onDelete(entry)}
              accessibilityRole="button"
              accessibilityHint="Long press to delete"
              scaleTo={0.985}
            >
              <Card style={styles.entryCard}>
                <View style={styles.entryText}>
                  <Text style={text.label} numberOfLines={1}>
                    {entry.food_name}
                  </Text>
                  <Text style={styles.entryMeta}>
                    {t(`slot.${entry.meal_slot}`)} ·{' '}
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
            </PressableScale>
          </EnterUp>
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

function QuickAddChip({
  food,
  busy,
  onPress,
}: {
  food: QuickAddFood;
  busy: boolean;
  onPress: () => void;
}) {
  const kcal = Math.round((food.kcal * food.last_quantity_grams) / 100);

  return (
    <PressableScale
      onPress={onPress}
      disabled={busy}
      accessibilityRole="button"
      accessibilityLabel={`Log ${Math.round(food.last_quantity_grams)} grams of ${food.name}`}
      style={[styles.chip, busy && styles.chipBusy]}
    >
      <View style={styles.chipPlus}>
        <Ionicons name={busy ? 'checkmark' : 'add'} size={15} color={color.accent} />
      </View>
      <View style={styles.chipText}>
        <Text style={styles.chipName} numberOfLines={1}>
          {food.name}
        </Text>
        {/* Both facts on the chip, because a one-tap action must show exactly
            what it will do before it is tapped. */}
        <Text style={styles.chipMeta}>
          {Math.round(food.last_quantity_grams)} g · {kcal} kcal
        </Text>
      </View>
    </PressableScale>
  );
}

function MacroTile({
  label,
  eaten,
  target,
  tint,
  surface,
  icon,
}: {
  label: string;
  eaten: number;
  target: number;
  tint: string;
  surface: string;
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
}) {
  const left = Math.round(target - eaten);
  const over = left < 0;
  const fraction = target > 0 ? eaten / target : 0;

  return (
    // Tinted rather than white. Three identical white tiles need their labels
    // read; three tinted ones are told apart peripherally, which is how they are
    // actually used — glanced at, not studied.
    <View style={[styles.macroTile, { backgroundColor: surface }]}>
      <View style={styles.macroHead}>
        <MaterialCommunityIcons name={icon} size={15} color={tint} />
        <Text style={styles.macroLabel}>{label}</Text>
      </View>
      <Text style={[styles.macroValue, { color: tint }]}>
        {Math.abs(left)}
        <Text style={styles.macroUnit}>g</Text>
      </Text>
      <Text style={styles.macroCaption}>{over ? 'over' : 'left'}</Text>
      <View style={styles.macroTrack}>
        <GrowBar fraction={fraction} tint={tint} height={5} />
      </View>
    </View>
  );
}

function MacroChip({ tint, value }: { tint: string; value: number }) {
  return (
    <View style={styles.macroDotRow}>
      <View style={[styles.chipDot, { backgroundColor: tint }]} />
      <Text style={styles.chipDotText}>{Math.round(value)}g</Text>
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
  greeting: { ...text.bodyMuted, fontSize: 13 },
  streakPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: color.flameTint,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
  },
  streakCount: { ...text.numeric, fontSize: 15, color: color.flame },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll: { paddingTop: space.lg, paddingBottom: 110, gap: space.md },
  errorCard: { marginTop: space.lg },
  errorBody: { marginTop: space.xs },

  calorieCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: space.xl,
  },
  calorieText: { gap: 2, flexShrink: 1 },
  calorieValue: {
    fontFamily: fontFamily.extraBold,
    fontSize: 46,
    letterSpacing: -1.4,
    color: color.ink,
  },
  calorieLabel: { ...text.label, fontSize: 15 },
  calorieSub: { ...text.bodyMuted, fontSize: 13, marginTop: space.xs },

  macroRow: { flexDirection: 'row', gap: space.md },
  macroTile: {
    flex: 1,
    gap: 2,
    padding: space.md,
    borderRadius: radius.lg,
  },
  macroHead: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  macroLabel: { ...text.overline, fontSize: 10, color: color.inkMuted },
  macroValue: { fontFamily: fontFamily.extraBold, fontSize: 22, letterSpacing: -0.5 },
  macroUnit: { fontFamily: fontFamily.bold, fontSize: 13 },
  macroCaption: { ...text.bodyMuted, fontSize: 11 },
  macroTrack: {
    height: 5,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(255, 255, 255, 0.65)',
    marginTop: space.sm,
    overflow: 'hidden',
  },

  quickAddBlock: { gap: space.sm },
  chipRail: { gap: space.sm, paddingRight: space.lg },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    maxWidth: 210,
    paddingLeft: space.sm,
    paddingRight: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    minHeight: HIT_SLOP_MIN,
    ...elevation.low,
  },
  chipBusy: { opacity: 0.6 },
  chipPlus: {
    width: 26,
    height: 26,
    borderRadius: radius.pill,
    backgroundColor: color.accentTint,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { flexShrink: 1 },
  chipName: { ...text.label, fontSize: 13 },
  chipMeta: { ...text.bodyMuted, fontSize: 11 },

  sectionTitle: { ...text.heading, marginTop: space.sm },

  suggestCard: { gap: space.md },
  suggestHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  suggestIcon: {
    width: 28,
    height: 28,
    borderRadius: radius.pill,
    backgroundColor: color.accentTint,
    alignItems: 'center',
    justifyContent: 'center',
  },
  suggestNote: { ...text.bodyMuted, fontSize: 13, lineHeight: 18 },
  suggestRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    paddingVertical: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.hairline,
  },
  suggestText: { flex: 1, gap: 2 },
  suggestReason: { ...text.bodyMuted, fontSize: 12, lineHeight: 16 },
  suggestAmount: { alignItems: 'flex-end' },
  suggestGrams: { ...text.numeric, fontSize: 15 },
  suggestKcal: { ...text.bodyMuted, fontSize: 11 },

  entryCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
  },
  entryText: { flex: 1, gap: 3 },
  entryMeta: { ...text.bodyMuted, fontSize: 12 },
  chipRow: { flexDirection: 'row', gap: space.sm, marginTop: space.xs },
  macroDotRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  chipDot: { width: 7, height: 7, borderRadius: radius.pill },
  chipDotText: { ...text.numeric, fontSize: 12, color: color.inkMuted },
  entryKcalBlock: { alignItems: 'flex-end' },
  entryKcalUnit: { ...text.bodyMuted, fontSize: 11 },

  emptyCard: { alignItems: 'center' },
  emptyPhoto: {
    width: '100%',
    height: 132,
    borderRadius: radius.md,
    marginBottom: space.md,
    backgroundColor: color.wash,
  },
  emptyBody: { marginTop: space.xs, fontSize: 13, textAlign: 'center' },
  partialNote: { ...text.bodyMuted, fontSize: 12, marginTop: space.sm },

  scrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(20, 22, 29, 0.20)',
  },
  menu: {
    position: 'absolute',
    right: space.xl,
    bottom: space.xl + 62 + space.md,
    alignItems: 'flex-end',
    gap: space.md,
  },
  menuRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  menuLabelPill: {
    backgroundColor: color.surface,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    ...elevation.mid,
  },
  menuLabel: { ...text.label, fontSize: 14 },
  menuIcon: {
    width: 50,
    height: 50,
    borderRadius: radius.pill,
    backgroundColor: color.accent,
    alignItems: 'center',
    justifyContent: 'center',
    ...elevation.mid,
  },

  fab: {
    position: 'absolute',
    right: space.xl,
    bottom: space.xl,
    width: 62,
    height: 62,
    borderRadius: radius.pill,
    backgroundColor: color.accent,
    alignItems: 'center',
    justifyContent: 'center',
    ...elevation.high,
  },
});
