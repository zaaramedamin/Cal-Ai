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

import { apiErrorMessage } from '@/api/errors';
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
import { type Translate, useLanguage } from '@/i18n';
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

// Functions of `t` rather than module constants, for the reason spelled out on
// `goalOptions` below: a constant would freeze whichever language happened to
// be loaded when the module was first imported.
function sexOptions(t: Translate): { value: Sex; label: string; description: string }[] {
  return [
    {
      value: 'female',
      label: t('onboarding.sexFemale'),
      description: t('onboarding.sexFemaleBody'),
    },
    { value: 'male', label: t('onboarding.sexMale'), description: t('onboarding.sexMaleBody') },
  ];
}

/** Labels are session counts — numerals, which need no translating. */
function activityOptions(
  t: Translate,
): { value: ActivityLevel; label: string; description: string }[] {
  return [
    { value: 'sedentary', label: '0', description: t('onboarding.activitySedentary') },
    { value: 'light', label: '1–2', description: t('onboarding.activityLight') },
    { value: 'moderate', label: '3–5', description: t('onboarding.activityModerate') },
    { value: 'active', label: '6–7', description: t('onboarding.activityActive') },
    { value: 'very_active', label: '7+', description: t('onboarding.activityVeryActive') },
  ];
}

/**
 * The four goals, as the user reads them.
 *
 * A function of `t` rather than a module constant, because the labels are
 * translated and a constant would freeze whichever language was loaded first.
 *
 * **The descriptions deliberately contain no numbers.** They used to read "20%
 * below maintenance", "10% above maintenance" and so on, which were the
 * multipliers the app applied before the pace step existed. Once pace set the
 * calorie target, those percentages described a calculation that no longer
 * happened — the exact drift the derived-target design exists to prevent. The
 * goal now states the intent and the pace step owns every figure, so there is
 * only one place a number can be wrong.
 */
function goalOptions(t: Translate): {
  value: Goal;
  label: string;
  description: string;
  icon: 'trending-down' | 'remove' | 'trending-up' | 'barbell';
}[] {
  return [
    {
      value: 'cut',
      label: t('onboarding.goalCut'),
      description: t('onboarding.goalCutBody'),
      icon: 'trending-down',
    },
    {
      value: 'maintain',
      label: t('onboarding.goalMaintain'),
      description: t('onboarding.goalMaintainBody'),
      icon: 'remove',
    },
    {
      value: 'lean_bulk',
      label: t('onboarding.goalLeanBulk'),
      description: t('onboarding.goalLeanBulkBody'),
      icon: 'trending-up',
    },
    {
      value: 'bulk',
      label: t('onboarding.goalBulk'),
      description: t('onboarding.goalBulkBody'),
      icon: 'barbell',
    },
  ];
}

/** Steps in order. `target` and `pace` are skipped when the goal is maintenance. */
const STEPS = ['sex', 'birth', 'body', 'activity', 'goal', 'target', 'pace', 'ready'] as const;
type Step = (typeof STEPS)[number];

/** Steps that only make sense when the weight is meant to move. */
const DIRECTIONAL_STEPS = new Set<Step>(['target', 'pace']);

export default function OnboardingScreen() {
  const router = useRouter();
  const { language, t } = useLanguage();

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
        apiErrorMessage(t, caught, 'onboarding.failed'),
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
            title={t('onboarding.sexTitle')}
            subtitle={t('onboarding.sexSubtitle')}
            footnote={t('onboarding.footnote')}
          >
            {sexOptions(t).map((option) => (
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
            title={t('onboarding.birthTitle')}
            subtitle={t('onboarding.birthSubtitle')}
            footnote={t('onboarding.footnote')}
          >
            <View style={styles.dateRow}>
              <View style={styles.dateSmall}>
                <TextField
                  label={t('onboarding.day')}
                  value={birthDay}
                  onChangeText={setBirthDay}
                  keyboardType="number-pad"
                  maxLength={2}
                  placeholder="20"
                />
              </View>
              <View style={styles.dateSmall}>
                <TextField
                  label={t('onboarding.month')}
                  value={birthMonth}
                  onChangeText={setBirthMonth}
                  keyboardType="number-pad"
                  maxLength={2}
                  placeholder="05"
                />
              </View>
              <View style={styles.dateLarge}>
                <TextField
                  label={t('onboarding.year')}
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
          <FunnelStep
            title={t('onboarding.bodyTitle')}
            subtitle={t('onboarding.bodySubtitle')}
            footnote={t('onboarding.footnote')}
          >
            <View style={styles.measure}>
              <View style={styles.measureHead}>
                <Text style={styles.measureLabel}>{t('body.height')}</Text>
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
                <Text style={styles.measureLabel}>{t('body.weight')}</Text>
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
            title={t('onboarding.activityTitle')}
            image="onboardingDone"
            subtitle={t('onboarding.activitySubtitle')}
            footnote={t('onboarding.footnote')}
          >
            {activityOptions(t).map((option) => (
              <ChoiceCard
                key={option.value}
                label={t('onboarding.sessionsPerWeek', { count: option.label })}
                description={option.description}
                selected={activity === option.value}
                onPress={() => setActivity(option.value)}
              />
            ))}
          </FunnelStep>
        )}

        {step === 'goal' && (
          <FunnelStep
            title={t('onboarding.goalTitle')}
            image="onboarding2"
            subtitle={t('onboarding.goalSubtitle')}
            footnote={t('onboarding.footnote')}
          >
            {goalOptions(t).map((option) => (
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
            title={t('onboarding.targetTitle')}
            image="onboarding1"
            subtitle={t('onboarding.targetSubtitle')}
            footnote={t('onboarding.footnote')}
          >
            {weightUnit === 'kg' ? (
              <RulerPicker
                {...WEIGHT_RANGE.kg}
                value={Math.round(targetKg)}
                onChange={setTargetKg}
                unit="kg"
                reference={{ value: weightKg, label: t('onboarding.rulerNow') }}
              />
            ) : (
              <RulerPicker
                {...WEIGHT_RANGE.lbs}
                value={Math.round(kgToLbs(targetKg))}
                onChange={(lbs) => setTargetKg(lbsToKg(lbs))}
                unit="lbs"
                reference={{ value: kgToLbs(weightKg), label: t('onboarding.rulerNow') }}
              />
            )}
          </FunnelStep>
        )}

        {step === 'pace' && (
          <FunnelStep
            title={t('onboarding.paceTitle')}
            subtitle={t('onboarding.paceSubtitle')}
            image="onboarding3"
            footnote={t('onboarding.footnote')}
          >
            {buildPaceOptions(weightKg, goal === 'maintain' ? null : targetKg, language).map(
              (option) => (
                <ChoiceCard
                  key={option.rateKg}
                  label={
                    option.arrival === null
                      ? t('onboarding.paceRate', { rate: option.rateKg })
                      : `${t('onboarding.paceRate', { rate: option.rateKg })} · ${option.arrival}`
                  }
                  // Assembled from parts joined by a separator rather than
                  // concatenated into a sentence. Each fragment is a complete
                  // phrase in its own language, so nothing depends on English
                  // word order to read correctly.
                  description={[
                    t('onboarding.paceDaily', {
                      sign: goal === 'cut' ? '−' : '+',
                      kcal: option.dailyKcal,
                    }),
                    option.weeks !== null
                      ? t('onboarding.paceWeeks', { weeks: option.weeks })
                      : null,
                    option.aggressive ? t('onboarding.paceAggressive') : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  selected={weeklyRateKg === option.rateKg}
                  onPress={() => setWeeklyRateKg(option.rateKg)}
                />
              ),
            )}
            <Text style={styles.illustrative}>{t('onboarding.paceCaveat')}</Text>
          </FunnelStep>
        )}

        {step === 'ready' && (
          <FunnelStep
            title={readyTitle(t, goal, weightKg, targetKg, weightUnit)}
            subtitle={t('onboarding.readySubtitle')}
          >
            <AchievementCurve />
            <View style={styles.curveAxis}>
              <Text style={styles.curveAxisLabel}>{t('onboarding.curveDay', { n: 1 })}</Text>
              <Text style={styles.curveAxisLabel}>{t('onboarding.curveDay', { n: 7 })}</Text>
              <Text style={styles.curveAxisLabel}>{t('onboarding.curveDay', { n: 30 })}</Text>
            </View>
            <Text style={styles.illustrative}>{t('onboarding.curveCaveat')}</Text>
          </FunnelStep>
        )}

        {error && (
          <View style={styles.errorBox} accessibilityRole="alert">
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
      </ScrollView>

      <Button
        label={isLast ? t('onboarding.finish') : t('onboarding.next')}
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

/**
 * The last step's heading, which changes with what was chosen.
 *
 * Four whole sentences rather than one with the verb swapped in. "drop" and
 * "gain" are one word apart in English and a different construction in French,
 * and a sentence assembled from a verb slot only ever reads correctly in the
 * language it was assembled for.
 */
function readyTitle(
  t: Translate,
  goal: Goal | null,
  weightKg: number,
  targetKg: number,
  unit: WeightUnit,
): string {
  if (goal === 'maintain') return t('onboarding.readyHold');
  const deltaKg = Math.abs(weightKg - targetKg);
  const shown = Math.round(unit === 'kg' ? deltaKg : kgToLbs(deltaKg));
  if (shown === 0) return t('onboarding.readyStart');
  const key = targetKg < weightKg ? 'onboarding.readyLose' : 'onboarding.readyGain';
  return t(key, { amount: shown, unit });
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
