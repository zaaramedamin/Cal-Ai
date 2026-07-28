/**
 * Onboarding funnel.
 *
 * One route holding every step rather than one route per step. Onboarding is a
 * single transaction — nothing is saved until the end — and separate routes
 * would let the hardware back button strand a user halfway through a form whose
 * state lives somewhere else. Here "back" is an index going down.
 *
 * **The one thing this funnel does differently from the apps it looks like.**
 *
 * Funnels in this category are built to convert, and the usual tricks are
 * fabricated social proof, a "without us" curve invented to look alarming, and a
 * projected date presented as a forecast. This one keeps the shape — the
 * progress bar, the cards, the encouragement steps, the projection chart —
 * because that shape genuinely makes a long form bearable. What it does not do
 * is dress an illustration up as data: the projection screen says in plain words
 * that the curve is illustrative and only the endpoints are calculated.
 */

import { useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import {
  type ActivityLevel,
  type Goal,
  type Sex,
  deviceTimezone,
  saveProfile,
} from '@/api/profile';
import { Button } from '@/components/button';
import { AchievementCurve, ChoiceCard, FunnelHeader, FunnelStep } from '@/components/funnel';
import { RulerPicker } from '@/components/ruler-picker';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { buildPaceOptions } from '@/features/onboarding/pace';
import {
  HEIGHT_RANGE,
  type HeightUnit,
  WEIGHT_RANGE,
  type WeightUnit,
  cmToInches,
  formatFeetInches,
  inchesToCm,
  kgToLbs,
  lbsToKg,
} from '@/lib/units';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { fontFamily, text } from '@/theme/typography';

const FOOTNOTE = 'Your measurements are stored only on your own account.';

const SEX_OPTIONS: { value: Sex; label: string; description: string }[] = [
  { value: 'female', label: 'Female', description: 'Uses the −161 constant' },
  { value: 'male', label: 'Male', description: 'Uses the +5 constant' },
];

const ACTIVITY_OPTIONS: {
  value: ActivityLevel;
  label: string;
  description: string;
}[] = [
  { value: 'sedentary', label: '0', description: 'Desk job, little or no exercise' },
  { value: 'light', label: '1–2', description: 'Workouts now and then' },
  { value: 'moderate', label: '3–5', description: 'A few workouts per week' },
  { value: 'active', label: '6–7', description: 'Hard exercise most days' },
  { value: 'very_active', label: '7+', description: 'Physical job, or training twice a day' },
];

const GOAL_OPTIONS: {
  value: Goal;
  label: string;
  description: string;
  icon: 'trending-down' | 'remove' | 'trending-up' | 'barbell';
}[] = [
  { value: 'cut', label: 'Lose fat', description: '20% below maintenance', icon: 'trending-down' },
  { value: 'maintain', label: 'Maintain', description: 'Eat at maintenance', icon: 'remove' },
  {
    value: 'lean_bulk',
    label: 'Lean bulk',
    description: '10% above maintenance',
    icon: 'trending-up',
  },
  { value: 'bulk', label: 'Bulk', description: '15% above maintenance', icon: 'barbell' },
];

/** Steps in order. `target` and `pace` are skipped when the goal is maintenance. */
const STEPS = ['sex', 'birth', 'body', 'activity', 'goal', 'target', 'pace', 'ready'] as const;
type Step = (typeof STEPS)[number];

/** Steps that only make sense when the weight is meant to move. */
const DIRECTIONAL_STEPS = new Set<Step>(['target', 'pace']);

export default function OnboardingScreen() {
  const router = useRouter();

  const [stepIndex, setStepIndex] = useState(0);
  const [sex, setSex] = useState<Sex | null>(null);
  const [birthYear, setBirthYear] = useState('');
  const [birthMonth, setBirthMonth] = useState('');
  const [birthDay, setBirthDay] = useState('');
  const [heightCm, setHeightCm] = useState(170);
  const [weightKg, setWeightKg] = useState(70);
  const [targetKg, setTargetKg] = useState(65);
  const [activity, setActivity] = useState<ActivityLevel | null>(null);
  const [goal, setGoal] = useState<Goal | null>(null);
  const [weeklyRateKg, setWeeklyRateKg] = useState<number | null>(null);

  const [heightUnit, setHeightUnit] = useState<HeightUnit>('cm');
  const [weightUnit, setWeightUnit] = useState<WeightUnit>('kg');

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Maintenance has no target weight, so that step is removed from the sequence
  // rather than shown and skipped — otherwise the progress bar jumps.
  const steps = useMemo(
    () =>
      STEPS.filter(
        (step) => !DIRECTIONAL_STEPS.has(step) || (goal !== null && goal !== 'maintain'),
      ),
    [goal],
  );
  const step: Step = steps[Math.min(stepIndex, steps.length - 1)];

  const birthDate = useMemo(() => {
    const y = Number(birthYear);
    const m = Number(birthMonth);
    const d = Number(birthDay);
    if (!y || !m || !d) return null;
    if (m < 1 || m > 12 || d < 1 || d > 31) return null;
    // Built as a plain string rather than a Date, because `new Date(...)` would
    // apply the device's timezone and could shift the day by one.
    return `${y.toString().padStart(4, '0')}-${m.toString().padStart(2, '0')}-${d
      .toString()
      .padStart(2, '0')}`;
  }, [birthYear, birthMonth, birthDay]);

  const canAdvance: Record<Step, boolean> = {
    sex: sex !== null,
    birth: birthDate !== null,
    body: heightCm > 0 && weightKg > 0,
    activity: activity !== null,
    goal: goal !== null,
    target: targetKg > 0,
    pace: weeklyRateKg !== null,
    ready: true,
  };

  const isLast = stepIndex === steps.length - 1;

  function goBack() {
    if (stepIndex === 0) router.back();
    else setStepIndex(stepIndex - 1);
  }

  async function finish() {
    if (!sex || !birthDate || !activity || !goal) return;
    setError(null);
    setSubmitting(true);
    try {
      await saveProfile({
        sex,
        birth_date: birthDate,
        height_cm: heightCm,
        weight_kg: weightKg,
        activity_level: activity,
        goal,
        target_weight_kg: goal === 'maintain' ? null : targetKg,
        // Null for maintenance, where a pace is incoherent — the server treats
        // it as zero for that goal anyway, but sending a number we skipped
        // asking about would be inventing an answer on the user's behalf.
        weekly_rate_kg: goal === 'maintain' ? null : weeklyRateKg,
        timezone: deviceTimezone(),
      });
      // The plan screen reads the saved profile back, so the numbers it shows
      // are the server's, not a client-side re-derivation that could drift.
      router.replace('/plan');
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.userMessage : 'Something went wrong. Try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      <FunnelHeader progress={(stepIndex + 1) / steps.length} onBack={goBack} />

      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {step === 'sex' && (
          <FunnelStep
            title="Which equation should we use?"
            subtitle="Mifflin-St Jeor uses a different constant for each. This is about body composition, not identity."
            footnote={FOOTNOTE}
          >
            {SEX_OPTIONS.map((option) => (
              <ChoiceCard
                key={option.value}
                label={option.label}
                description={option.description}
                selected={sex === option.value}
                onPress={() => setSex(option.value)}
              />
            ))}
          </FunnelStep>
        )}

        {step === 'birth' && (
          <FunnelStep
            title="When were you born?"
            subtitle="Metabolic rate falls gradually with age, so the date matters more than you'd think."
            footnote={FOOTNOTE}
          >
            <View style={styles.dateRow}>
              <View style={styles.dateSmall}>
                <TextField
                  label="Day"
                  value={birthDay}
                  onChangeText={setBirthDay}
                  keyboardType="number-pad"
                  maxLength={2}
                  placeholder="20"
                />
              </View>
              <View style={styles.dateSmall}>
                <TextField
                  label="Month"
                  value={birthMonth}
                  onChangeText={setBirthMonth}
                  keyboardType="number-pad"
                  maxLength={2}
                  placeholder="05"
                />
              </View>
              <View style={styles.dateLarge}>
                <TextField
                  label="Year"
                  value={birthYear}
                  onChangeText={setBirthYear}
                  keyboardType="number-pad"
                  maxLength={4}
                  placeholder="1996"
                />
              </View>
            </View>
          </FunnelStep>
        )}

        {step === 'body' && (
          <FunnelStep title="Height & weight" subtitle="Both feed the calculation." footnote={FOOTNOTE}>
            <View style={styles.measure}>
              <View style={styles.measureHead}>
                <Text style={styles.measureLabel}>Height</Text>
                <UnitToggle
                  options={[
                    { value: 'ftin', label: 'ft/in' },
                    { value: 'cm', label: 'cm' },
                  ]}
                  value={heightUnit}
                  onChange={setHeightUnit}
                />
              </View>
              {heightUnit === 'cm' ? (
                <RulerPicker
                  {...HEIGHT_RANGE.cm}
                  value={Math.round(heightCm)}
                  onChange={setHeightCm}
                  unit="cm"
                />
              ) : (
                <RulerPicker
                  {...HEIGHT_RANGE.ftin}
                  value={Math.round(cmToInches(heightCm))}
                  onChange={(inches) => setHeightCm(inchesToCm(inches))}
                  formatValue={formatFeetInches}
                />
              )}
            </View>

            <View style={styles.measure}>
              <View style={styles.measureHead}>
                <Text style={styles.measureLabel}>Weight</Text>
                <UnitToggle
                  options={[
                    { value: 'lbs', label: 'lbs' },
                    { value: 'kg', label: 'kg' },
                  ]}
                  value={weightUnit}
                  onChange={setWeightUnit}
                />
              </View>
              {weightUnit === 'kg' ? (
                <RulerPicker
                  {...WEIGHT_RANGE.kg}
                  value={Math.round(weightKg)}
                  onChange={(kg) => {
                    setWeightKg(kg);
                    setTargetKg((current) => (current === 0 ? kg : current));
                  }}
                  unit="kg"
                />
              ) : (
                <RulerPicker
                  {...WEIGHT_RANGE.lbs}
                  value={Math.round(kgToLbs(weightKg))}
                  onChange={(lbs) => setWeightKg(lbsToKg(lbs))}
                  unit="lbs"
                />
              )}
            </View>
          </FunnelStep>
        )}

        {step === 'activity' && (
          <FunnelStep
            title="How often do you train?"
            subtitle="Be honest — overestimating here is the single most common reason a calorie target comes out too high."
            footnote={FOOTNOTE}
          >
            {ACTIVITY_OPTIONS.map((option) => (
              <ChoiceCard
                key={option.value}
                label={`${option.label} sessions a week`}
                description={option.description}
                selected={activity === option.value}
                onPress={() => setActivity(option.value)}
              />
            ))}
          </FunnelStep>
        )}

        {step === 'goal' && (
          <FunnelStep
            title="What are you aiming for?"
            subtitle="This sets how far your target sits from maintenance."
            footnote={FOOTNOTE}
          >
            {GOAL_OPTIONS.map((option) => (
              <ChoiceCard
                key={option.value}
                icon={option.icon}
                label={option.label}
                description={option.description}
                selected={goal === option.value}
                onPress={() => {
                  setGoal(option.value);
                  // Seed a sensible target so the ruler does not open on a value
                  // that contradicts the goal just chosen.
                  setTargetKg(
                    option.value === 'cut'
                      ? Math.max(WEIGHT_RANGE.kg.min, Math.round(weightKg * 0.9))
                      : Math.round(weightKg * 1.08),
                  );
                  // Open the pace picker on the sensible default for this goal,
                  // matching DEFAULT_WEEKLY_RATE_KG on the server. Lean bulk is
                  // slower on purpose: past ~0.25 kg a week the extra is fat.
                  setWeeklyRateKg(option.value === 'lean_bulk' ? 0.25 : 0.5);
                }}
              />
            ))}
          </FunnelStep>
        )}

        {step === 'target' && (
          <FunnelStep
            title="What weight are you aiming for?"
            subtitle="Used for the projection below. Your calorie target comes from your goal, not from this number."
            footnote={FOOTNOTE}
          >
            {weightUnit === 'kg' ? (
              <RulerPicker
                {...WEIGHT_RANGE.kg}
                value={Math.round(targetKg)}
                onChange={setTargetKg}
                unit="kg"
                reference={{ value: weightKg, label: 'Now' }}
              />
            ) : (
              <RulerPicker
                {...WEIGHT_RANGE.lbs}
                value={Math.round(kgToLbs(targetKg))}
                onChange={(lbs) => setTargetKg(lbsToKg(lbs))}
                unit="lbs"
                reference={{ value: kgToLbs(weightKg), label: 'Now' }}
              />
            )}
          </FunnelStep>
        )}

        {step === 'pace' && (
          <FunnelStep
            title="How fast do you want to get there?"
            subtitle="This is what actually sets your daily calories. Slower is easier to keep up, and keeping it up is the whole thing."
            footnote={FOOTNOTE}
          >
            {buildPaceOptions(weightKg, goal === 'maintain' ? null : targetKg).map((option) => (
              <ChoiceCard
                key={option.rateKg}
                label={option.label}
                description={
                  `${goal === 'cut' ? '−' : '+'}${option.dailyKcal} kcal a day` +
                  (option.weeks !== null ? ` · about ${option.weeks} weeks` : '') +
                  (option.aggressive ? ' · faster than 1% of your bodyweight' : '')
                }
                selected={weeklyRateKg === option.rateKg}
                onPress={() => setWeeklyRateKg(option.rateKg)}
              />
            ))}
            <Text style={styles.illustrative}>
              Projections assume a steady pace and about 7,700 kcal per kilogram. Real bodies are
              less tidy — treat the scale over a few weeks as the real answer.
            </Text>
          </FunnelStep>
        )}

        {step === 'ready' && (
          <FunnelStep
            title={readyTitle(goal, weightKg, targetKg, weightUnit)}
            subtitle="People who log consistently in the first week are far more likely to still be logging in the second. The first few days are the whole game."
          >
            <AchievementCurve />
            <View style={styles.curveAxis}>
              <Text style={styles.curveAxisLabel}>Day 1</Text>
              <Text style={styles.curveAxisLabel}>Day 7</Text>
              <Text style={styles.curveAxisLabel}>Day 30</Text>
            </View>
            <Text style={styles.illustrative}>
              Illustrative — it shows the habit curve, not a prediction about you.
            </Text>
          </FunnelStep>
        )}

        {error && (
          <View style={styles.errorBox} accessibilityRole="alert">
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
      </ScrollView>

      <Button
        label={isLast ? 'Build my plan' : 'Next'}
        disabled={!canAdvance[step]}
        loading={submitting}
        onPress={() => {
          if (isLast) void finish();
          else setStepIndex(stepIndex + 1);
        }}
      />
    </Screen>
  );
}

function readyTitle(
  goal: Goal | null,
  weightKg: number,
  targetKg: number,
  unit: WeightUnit,
): string {
  if (goal === 'maintain') return 'Ready to hold steady?';
  const deltaKg = Math.abs(weightKg - targetKg);
  const shown = Math.round(unit === 'kg' ? deltaKg : kgToLbs(deltaKg));
  if (shown === 0) return 'Ready to start?';
  const verb = targetKg < weightKg ? 'drop' : 'gain';
  return `Ready to ${verb} ${shown} ${unit}?`;
}

function UnitToggle<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <View style={styles.toggle}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            onPress={() => onChange(option.value)}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            style={[styles.toggleOption, selected && styles.toggleOptionSelected]}
          >
            <Text style={[styles.toggleLabel, selected && styles.toggleLabelSelected]}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { flexGrow: 1, paddingBottom: space.lg },

  dateRow: { flexDirection: 'row', gap: space.md },
  dateSmall: { flex: 1 },
  dateLarge: { flex: 1.4 },

  measure: { gap: space.sm },
  measureHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  measureLabel: { fontFamily: fontFamily.bold, fontSize: 17, color: color.ink },

  toggle: { flexDirection: 'row', backgroundColor: color.wash, borderRadius: radius.pill, padding: 3 },
  toggleOption: {
    minWidth: 54,
    minHeight: HIT_SLOP_MIN - 12,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
  },
  toggleOptionSelected: { backgroundColor: color.accent },
  toggleLabel: { ...text.label, fontSize: 13, color: color.inkMuted },
  toggleLabelSelected: { color: color.onDark },

  curveAxis: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: space.lg },
  curveAxisLabel: { ...text.bodyMuted, fontSize: 12 },
  illustrative: { ...text.bodyMuted, fontSize: 11, textAlign: 'center', marginTop: space.sm },

  errorBox: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.danger,
  },
  errorText: { ...text.body, fontSize: 14 },
});
