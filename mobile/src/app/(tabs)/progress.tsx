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
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import Svg, { Defs, LinearGradient, Path, Stop } from 'react-native-svg';

import { ApiError } from '@/api/client';
import { logWeight } from '@/api/profile';
import { type Progress, getProgress } from '@/api/progress';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { color, radius, space } from '@/theme/tokens';
import { fontFamily, text } from '@/theme/typography';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; progress: Progress }
  | { kind: 'error'; message: string };

export default function ProgressScreen() {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [weightInput, setWeightInput] = useState('');
  const [savingWeight, setSavingWeight] = useState(false);

  const load = useCallback(async () => {
    try {
      setState({ kind: 'ready', progress: await getProgress() });
    } catch (caught) {
      setState({
        kind: 'error',
        message:
          caught instanceof ApiError ? caught.userMessage : 'Could not load your progress.',
      });
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  async function handleLogWeight() {
    const value = Number(weightInput);
    if (!Number.isFinite(value) || value <= 0) return;
    setSavingWeight(true);
    try {
      await logWeight(value);
      setWeightInput('');
      await load();
    } catch {
      /* the reload above simply doesn't happen; the field keeps its value */
    } finally {
      setSavingWeight(false);
    }
  }

  return (
    <Screen>
      <Text style={text.title}>Progress</Text>

      {state.kind === 'loading' && (
        <View style={styles.centered}>
          <Text style={text.bodyMuted}>Loading…</Text>
        </View>
      )}

      {state.kind === 'error' && (
        <Card style={styles.gapTop}>
          <Text style={text.label}>Can&apos;t load progress</Text>
          <Text style={[text.bodyMuted, styles.errorBody]}>{state.message}</Text>
        </Card>
      )}

      {state.kind === 'ready' && (
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          {/* Streak */}
          <Card style={styles.streakCard}>
            <View style={styles.streakFlame}>
              <Ionicons name="flame" size={34} color={color.flame} />
            </View>
            <View style={styles.streakText}>
              <Text style={text.heading}>
                {state.progress.streak_days} day
                {state.progress.streak_days === 1 ? '' : 's'} streak
              </Text>
              <Text style={[text.bodyMuted, styles.streakSub]}>
                {state.progress.logged_today
                  ? 'Today is logged — keep it rolling.'
                  : state.progress.streak_days > 0
                    ? "Log something today to keep it alive."
                    : 'Log a meal today to start one.'}
              </Text>
            </View>
          </Card>

          {/* Weight */}
          <Card>
            <View style={styles.cardHeader}>
              <Text style={text.heading}>Weight</Text>
              {state.progress.current_weight_kg !== null && (
                <Text style={text.heading}>{state.progress.current_weight_kg} kg</Text>
              )}
            </View>

            {state.progress.target_weight_kg !== null &&
              state.progress.current_weight_kg !== null && (
                <Text style={[text.bodyMuted, styles.goalLine]}>
                  Goal {state.progress.target_weight_kg} kg ·{' '}
                  {Math.abs(
                    state.progress.current_weight_kg - state.progress.target_weight_kg,
                  ).toFixed(1)}{' '}
                  kg to go
                </Text>
              )}

            <WeightChart points={state.progress.weight_series.map((p) => p.weight_kg)} />

            <View style={styles.weightForm}>
              <View style={styles.weightField}>
                <TextField
                  label="Today's weight (kg)"
                  value={weightInput}
                  onChangeText={setWeightInput}
                  keyboardType="decimal-pad"
                  placeholder={
                    state.progress.current_weight_kg !== null
                      ? String(state.progress.current_weight_kg)
                      : '80'
                  }
                />
              </View>
              <Button
                label="Log"
                onPress={() => void handleLogWeight()}
                loading={savingWeight}
                disabled={!Number(weightInput)}
              />
            </View>
          </Card>

          {/* BMI */}
          {state.progress.bmi !== null && state.progress.bmi_category !== null && (
            <Card>
              <View style={styles.cardHeader}>
                <Text style={text.heading}>BMI</Text>
                <Text style={text.heading}>{state.progress.bmi}</Text>
              </View>
              <Text style={[text.bodyMuted, styles.bmiCategory]}>
                Your weight is{' '}
                <Text style={styles.bmiCategoryStrong}>{state.progress.bmi_category}</Text>
              </Text>
              <BmiScale bmi={state.progress.bmi} />
              <Text style={styles.bmiCaveat}>
                BMI ignores body composition — muscular people read high. Treat it as one
                signal, not a verdict.
              </Text>
            </Card>
          )}

          {/* This week */}
          <Card>
            <View style={styles.cardHeader}>
              <Text style={text.heading}>This week</Text>
              <Text style={[text.bodyMuted, styles.weekAvg]}>
                avg {Math.round(state.progress.weekly_average_kcal).toLocaleString()} kcal
              </Text>
            </View>
            <WeekBars days={state.progress.last_7_days.map((d) => d.kcal)} />
          </Card>
        </ScrollView>
      )}
    </Screen>
  );
}

/** One polyline over a soft gradient — the whole chart. */
function WeightChart({ points }: { points: number[] }) {
  const WIDTH = 280;
  const HEIGHT = 90;

  if (points.length < 2) {
    return (
      <Text style={styles.chartEmpty}>
        Log your weight a few times and the trend appears here.
      </Text>
    );
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  // A flat line at mid-height when every reading is identical; a padded range
  // otherwise so the line never touches the card edges.
  const span = max - min || 1;
  const step = WIDTH / (points.length - 1);

  const coords = points.map((value, index) => ({
    x: index * step,
    y: 8 + (HEIGHT - 16) * (1 - (value - min) / span),
  }));
  const line = coords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  const area = `${line} L${WIDTH},${HEIGHT} L0,${HEIGHT} Z`;

  return (
    <Svg width="100%" height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
      <Defs>
        <LinearGradient id="weightFill" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={color.ink} stopOpacity="0.12" />
          <Stop offset="1" stopColor={color.ink} stopOpacity="0" />
        </LinearGradient>
      </Defs>
      <Path d={area} fill="url(#weightFill)" />
      <Path d={line} stroke={color.ink} strokeWidth={2.5} fill="none" strokeLinecap="round" />
    </Svg>
  );
}

const BMI_BANDS = [
  { to: 18.5, tint: color.fat },
  { to: 25, tint: color.positive },
  { to: 30, tint: color.carbs },
  { to: 40, tint: color.danger },
];

/** The standard four-band scale with a marker at the user's value. */
function BmiScale({ bmi }: { bmi: number }) {
  const MIN = 14;
  const MAX = 40;
  const clamped = Math.max(MIN, Math.min(MAX, bmi));
  const position = ((clamped - MIN) / (MAX - MIN)) * 100;

  let start = MIN;
  return (
    <View style={styles.bmiScaleWrap}>
      <View style={styles.bmiScale}>
        {BMI_BANDS.map((band) => {
          const width = ((band.to - start) / (MAX - MIN)) * 100;
          start = band.to;
          return (
            <View
              key={band.to}
              style={{ width: `${width}%`, backgroundColor: band.tint }}
            />
          );
        })}
      </View>
      <View style={[styles.bmiMarker, { left: `${position}%` }]} />
    </View>
  );
}

/** Seven bars, tallest = biggest day. Zero-days render a stub so the week keeps
 * its shape. */
function WeekBars({ days }: { days: number[] }) {
  const max = Math.max(...days, 1);
  const LETTERS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
  const today = new Date().getDay();

  return (
    <View style={styles.weekRow}>
      {days.map((kcal, index) => {
        // days[] ends today; work each bar's weekday backwards from that.
        const weekday = (today - (days.length - 1 - index) + 7) % 7;
        return (
          <View key={index} style={styles.weekBarSlot}>
            <View style={styles.weekBarTrack}>
              <View
                style={[
                  styles.weekBarFill,
                  { height: `${Math.max(4, (kcal / max) * 100)}%` },
                  kcal === 0 && styles.weekBarEmpty,
                ]}
              />
            </View>
            <Text style={styles.weekBarLabel}>{LETTERS[weekday]}</Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll: { paddingTop: space.lg, paddingBottom: space.xxl, gap: space.md },
  gapTop: { marginTop: space.lg },
  errorBody: { marginTop: space.xs },

  streakCard: { flexDirection: 'row', alignItems: 'center', gap: space.lg },
  streakFlame: {
    width: 60,
    height: 60,
    borderRadius: radius.pill,
    backgroundColor: color.wash,
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
  chartEmpty: { ...text.bodyMuted, fontSize: 13, paddingVertical: space.lg },
  weightForm: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: space.md,
    marginTop: space.lg,
  },
  weightField: { flex: 1 },

  bmiCategory: { fontSize: 14, marginBottom: space.md },
  bmiCategoryStrong: { fontFamily: fontFamily.semiBold, color: color.ink },
  bmiScaleWrap: { position: 'relative', marginBottom: space.md },
  bmiScale: {
    flexDirection: 'row',
    height: 8,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  bmiMarker: {
    position: 'absolute',
    top: -3,
    width: 3,
    height: 14,
    borderRadius: radius.pill,
    backgroundColor: color.ink,
    marginLeft: -1.5,
  },
  bmiCaveat: { ...text.bodyMuted, fontSize: 12, lineHeight: 17 },

  weekAvg: { fontSize: 13 },
  weekRow: { flexDirection: 'row', gap: space.sm, height: 96 },
  weekBarSlot: { flex: 1, alignItems: 'center', gap: space.xs },
  weekBarTrack: { flex: 1, width: 14, justifyContent: 'flex-end' },
  weekBarFill: {
    width: '100%',
    borderRadius: radius.pill,
    backgroundColor: color.ink,
  },
  weekBarEmpty: { backgroundColor: color.wash },
  weekBarLabel: { ...text.overline, fontSize: 10 },
});
