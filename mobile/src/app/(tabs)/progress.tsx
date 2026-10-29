/**
 * Progress — streak, weight trend, BMI and the week's intake.
 *
 * All four cards come from one endpoint, fetched once per focus. The weight
 * chart is drawn directly with SVG rather than a chart library: it is one
 * polyline with a gradient fill, and a charting dependency would be megabytes
 * of API for exactly this.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { apiErrorMessage } from '@/api/errors';
import { logWeight } from '@/api/profile';
import { type Progress, getProgress } from '@/api/progress';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Screen } from '@/components/screen';
import { BmiCard } from '@/features/progress/bmi-card';
import { WeightChangesCard } from '@/features/progress/weight-changes-card';
import { TAB_DOCK_HEIGHT } from '@/components/tab-bar';
import { TextField } from '@/components/text-field';
import { TrendChart } from '@/components/trend-chart';
import { type Translate, useT } from '@/i18n';
import { WEEKDAY_KEYS } from '@/i18n/strings';
import { parseDecimal } from '@/lib/units';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; progress: Progress }
  | { kind: 'error'; message: string };

export default function ProgressScreen() {
  const t = useT();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [weightInput, setWeightInput] = useState('');
  const [savingWeight, setSavingWeight] = useState(false);
  const [weightError, setWeightError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // parseDecimal, not Number: the French keypad's decimal key is a comma, so
  // "72,5" used to disable the button and could never be logged.
  const weightValue = parseDecimal(weightInput);
  const weightValid = weightValue !== null && weightValue > 0;

  const load = useCallback(async () => {
    try {
      setState({ kind: 'ready', progress: await getProgress() });
    } catch (caught) {
      setState({
        kind: 'error',
        message: apiErrorMessage(t, caught, 'progress.loadFailed'),
      });
    }
  }, [t]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  async function handleLogWeight() {
    if (!weightValid || weightValue === null) return;
    setSavingWeight(true);
    setWeightError(null);
    try {
      await logWeight(weightValue);
      setWeightInput('');
      await load();
    } catch {
      // Said, not swallowed. The field keeps its value either way, but a
      // button that silently does nothing reads as a button that is broken.
      setWeightError(t('progress.weightFailed'));
    } finally {
      setSavingWeight(false);
    }
  }

  async function refresh() {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }

  function retry() {
    setState({ kind: 'loading' });
    void load();
  }

  return (
    <Screen>
      <Text style={text.title}>{t('progress.title')}</Text>

      {state.kind === 'loading' && (
        <View style={styles.centered}>
          <ActivityIndicator color={color.accent} />
          <Text style={text.bodyMuted}>{t('common.loading')}</Text>
        </View>
      )}

      {state.kind === 'error' && (
        <Card style={styles.gapTop}>
          <Text style={text.label}>{t('progress.cantLoad')}</Text>
          <Text style={[text.bodyMuted, styles.errorBody]}>{state.message}</Text>
          <View style={styles.errorAction}>
            <Button label={t('common.retry')} variant="secondary" onPress={retry} />
          </View>
        </Card>
      )}

      {state.kind === 'ready' && (
        <ScrollView
          contentContainerStyle={styles.scroll}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
          automaticallyAdjustKeyboardInsets
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => void refresh()}
              tintColor={color.accent}
              colors={[color.accent]}
            />
          }
        >
          {/* Streak */}
          <Card style={styles.streakCard}>
            <View style={styles.streakFlame}>
              <Ionicons name="flame" size={34} color={color.flame} />
            </View>
            <View style={styles.streakText}>
              <Text style={text.heading}>
                {state.progress.streak_days === 1
                  ? t('progress.streakOne')
                  : t('progress.streakMany', { count: state.progress.streak_days })}
              </Text>
              <Text style={[text.bodyMuted, styles.streakSub]}>
                {state.progress.logged_today
                  ? t('progress.streakLogged')
                  : state.progress.streak_days > 0
                    ? t('progress.streakKeepAlive')
                    : t('progress.streakStart')}
              </Text>
            </View>
          </Card>

          {/* Weight */}
          <Card>
            <View style={styles.cardHeader}>
              <Text style={text.heading}>{t('progress.weight')}</Text>
              {state.progress.current_weight_kg !== null && (
                <Text style={text.heading}>{state.progress.current_weight_kg} kg</Text>
              )}
            </View>

            {state.progress.target_weight_kg !== null &&
              state.progress.current_weight_kg !== null && (
                <Text style={[text.bodyMuted, styles.goalLine]}>
                  {t('progress.goalLine', {
                    target: state.progress.target_weight_kg,
                    remaining: Math.abs(
                      state.progress.current_weight_kg - state.progress.target_weight_kg,
                    ).toFixed(1),
                  })}
                </Text>
              )}

            <TrendChart
              values={state.progress.weight_series.map((p) => p.weight_kg)}
              target={state.progress.target_weight_kg}
            />

            <View style={styles.weightForm}>
              <View style={styles.weightField}>
                <TextField
                  label={t('progress.todaysWeight')}
                  value={weightInput}
                  onChangeText={(next) => {
                    setWeightInput(next);
                    setWeightError(null);
                  }}
                  keyboardType="decimal-pad"
                  placeholder={
                    state.progress.current_weight_kg !== null
                      ? String(state.progress.current_weight_kg)
                      : '80'
                  }
                />
              </View>
              <Button
                label={t('progress.logWeight')}
                onPress={() => void handleLogWeight()}
                loading={savingWeight}
                disabled={!weightValid}
              />
            </View>
            {weightError && (
              <Text style={styles.weightError} accessibilityRole="alert">
                {weightError}
              </Text>
            )}
          </Card>

          {/* How fast the weight is actually moving. Six subtractions, which is
              a better answer to "am I making progress" than the chart above. */}
          <WeightChangesCard series={state.progress.weight_series} />

          {state.progress.bmi !== null && state.progress.bmi_category !== null && (
            <BmiCard bmi={state.progress.bmi} category={state.progress.bmi_category} />
          )}

          {/* This week */}
          <Card>
            <View style={styles.cardHeader}>
              <Text style={text.heading}>{t('progress.thisWeek')}</Text>
              <Text style={[text.bodyMuted, styles.weekAvg]}>
                {t('progress.weekAverage', {
                  kcal: Math.round(state.progress.weekly_average_kcal).toLocaleString(),
                })}
              </Text>
            </View>
            <WeekBars
              t={t}
              days={state.progress.last_7_days.map((d) => d.kcal)}
              target={state.progress.target_calories || null}
            />
          </Card>
        </ScrollView>
      )}
    </Screen>
  );
}


/**
 * Seven bars with the daily target drawn across them.
 *
 * The target line is what turns this from a picture into an answer. Bar heights
 * alone say "Tuesday was the big day"; the line says whether Tuesday was over
 * budget, which is the question someone actually opens this card to ask. Bars
 * are tinted by which side of it they land on.
 *
 * Zero-days render a stub rather than nothing, so an unlogged day is visibly a
 * gap in the week instead of a day that silently disappears.
 */
function WeekBars({
  days,
  target,
  t,
}: {
  days: number[];
  target: number | null;
  t: Translate;
}) {
  const LETTERS = WEEKDAY_KEYS.map((key) => t(key));
  const today = new Date().getDay();

  // The scale has to include the target, or a week spent under it would push the
  // line off the top of the card and hide the very comparison being made.
  const max = Math.max(...days, target ?? 0, 1) * 1.1;
  const targetPercent = target ? (target / max) * 100 : null;

  // days[] ends today; work each bar's weekday backwards from that.
  const weekdayOf = (index: number) => (today - (days.length - 1 - index) + 7) % 7;

  return (
    <View>
      {/* The bars and the target line share one box, so a percentage means the
          same height for both. The line used to be positioned against the whole
          row — bars *and* the day letters under them — while the bars filled
          only the part above the letters, so a day exactly on target drew well
          short of the line that was supposed to mark it. */}
      <View style={styles.weekPlot}>
        {targetPercent !== null && (
          <View pointerEvents="none" style={[styles.targetLine, { bottom: `${targetPercent}%` }]}>
            <View style={styles.targetDash} />
          </View>
        )}
        {days.map((kcal, index) => {
          const over = target !== null && kcal > target;
          return (
            <View key={index} style={styles.weekBarSlot}>
              <View
                style={[
                  styles.weekBarFill,
                  { height: `${Math.max(4, (kcal / max) * 100)}%` },
                  over && styles.weekBarOver,
                  kcal === 0 && styles.weekBarEmpty,
                ]}
              />
            </View>
          );
        })}
      </View>
      <View style={styles.weekLabels}>
        {days.map((_, index) => (
          <Text key={index} style={styles.weekBarLabel}>
            {LETTERS[weekdayOf(index)]}
          </Text>
        ))}
      </View>
      {target !== null && (
        <Text style={styles.targetCaption}>
          {t('progress.targetCaption', { kcal: Math.round(target).toLocaleString() })}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.sm },
  // Clears the floating tab bar, which overlays the content.
  scroll: { paddingTop: space.lg, paddingBottom: TAB_DOCK_HEIGHT + space.xl, gap: space.md },
  gapTop: { marginTop: space.lg },
  errorBody: { marginTop: space.xs },
  errorAction: { marginTop: space.lg },

  streakCard: { flexDirection: 'row', alignItems: 'center', gap: space.lg },
  streakFlame: {
    width: 60,
    height: 60,
    borderRadius: radius.pill,
    // The flame's own tint, matching the streak pill on Home. It was the grey
    // wash here — the one place the flame sat on grey.
    backgroundColor: color.flameTint,
    alignItems: 'center',
    justifyContent: 'center',
  },
  streakText: { flex: 1, gap: 2 },
  streakSub: { fontSize: 13 },

  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: space.sm,
  },
  goalLine: { fontSize: 13, marginBottom: space.md },
  weightForm: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: space.md,
    marginTop: space.lg,
  },
  weightField: { flex: 1 },
  weightError: { ...text.label, fontSize: 13, color: color.dangerText, marginTop: space.sm },

  weekAvg: { fontSize: 13 },
  weekPlot: { flexDirection: 'row', gap: space.sm, height: 80, position: 'relative' },
  // Spans the full row so the comparison reads across the whole week rather
  // than bar by bar.
  targetLine: { position: 'absolute', left: 0, right: 0, zIndex: 1 },
  targetDash: {
    height: 0,
    borderTopWidth: 1.5,
    borderStyle: 'dashed',
    borderTopColor: color.inkMuted,
  },
  targetCaption: { ...text.bodyMuted, fontSize: 11, marginTop: space.sm },
  weekBarSlot: { flex: 1, alignItems: 'center', justifyContent: 'flex-end' },
  weekBarFill: {
    width: 14,
    borderRadius: radius.pill,
    backgroundColor: color.accent,
  },
  weekBarOver: { backgroundColor: color.warning },
  weekBarEmpty: { backgroundColor: color.wash },
  weekLabels: { flexDirection: 'row', gap: space.sm, marginTop: space.xs },
  weekBarLabel: { ...text.overline, fontSize: 11, flex: 1, textAlign: 'center' },
});
