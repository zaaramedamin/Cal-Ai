/**
 * Onboarding: body stats and goal, then targets.
 *
 * One route holding several steps rather than one route per step. Onboarding is
 * a single transaction — nothing is saved until the end — and separate routes
 * would let the hardware back button strand a user halfway through a form whose
 * state lives somewhere else. Here "back" is just an index going down.
 */

import { useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { ApiError } from '@/api/client';
import {
  type ActivityLevel,
  type Goal,
  type Sex,
  deviceTimezone,
  saveProfile,
} from '@/api/profile';
import { Button } from '@/components/button';
import { OptionList, type Option } from '@/components/option-list';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { HOME } from '@/routes';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

const SEX_OPTIONS: readonly Option<Sex>[] = [
  { value: 'female', label: 'Female' },
  { value: 'male', label: 'Male' },
];

const ACTIVITY_OPTIONS: readonly Option<ActivityLevel>[] = [
  { value: 'sedentary', label: 'Sedentary', description: 'Desk job, little or no exercise' },
  { value: 'light', label: 'Light', description: 'Light exercise 1–3 days a week' },
  { value: 'moderate', label: 'Moderate', description: 'Moderate exercise 3–5 days a week' },
  { value: 'active', label: 'Active', description: 'Hard exercise 6–7 days a week' },
  {
    value: 'very_active',
    label: 'Very active',
    description: 'Physical job, or training twice a day',
  },
];

const GOAL_OPTIONS: readonly Option<Goal>[] = [
  { value: 'cut', label: 'Lose fat', description: '20% below maintenance' },
  { value: 'maintain', label: 'Maintain', description: 'Eat at maintenance' },
  { value: 'lean_bulk', label: 'Lean bulk', description: '10% above maintenance' },
  { value: 'bulk', label: 'Bulk', description: '15% above maintenance' },
];

const STEP_COUNT = 5;

export default function OnboardingScreen() {
  const router = useRouter();

  const [step, setStep] = useState(0);
  const [sex, setSex] = useState<Sex | null>(null);
  const [birthYear, setBirthYear] = useState('');
  const [birthMonth, setBirthMonth] = useState('');
  const [birthDay, setBirthDay] = useState('');
  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [activity, setActivity] = useState<ActivityLevel | null>(null);
  const [goal, setGoal] = useState<Goal | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const birthDate = useMemo(() => {
    const y = Number(birthYear);
    const m = Number(birthMonth);
    const d = Number(birthDay);
    if (!y || !m || !d) return null;
    if (m < 1 || m > 12 || d < 1 || d > 31) return null;
    // Constructed as a plain string rather than a Date, because `new Date(...)`
    // would apply the device's timezone and could shift the day by one.
    return `${y.toString().padStart(4, '0')}-${m.toString().padStart(2, '0')}-${d
      .toString()
      .padStart(2, '0')}`;
  }, [birthYear, birthMonth, birthDay]);

  const height = Number(heightCm);
  const weight = Number(weightKg);

  // Each step knows only whether it is complete. Validation of *ranges* is left
  // to the server and the shared targets module — duplicating the bounds here
  // would create a second definition that drifts.
  const canAdvance = [
    sex !== null,
    birthDate !== null,
    Number.isFinite(height) && height > 0,
    Number.isFinite(weight) && weight > 0,
    activity !== null && goal !== null,
  ][step];

  async function handleFinish() {
    if (!sex || !birthDate || !activity || !goal) return;
    setError(null);
    setSubmitting(true);
    try {
      await saveProfile({
        sex,
        birth_date: birthDate,
        height_cm: height,
        weight_kg: weight,
        activity_level: activity,
        goal,
        timezone: deviceTimezone(),
      });
      // The dashboard refetches on focus, so it will show the new targets.
      router.replace(HOME);
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
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <ProgressDots total={STEP_COUNT} current={step} />

          {step === 0 && (
            <StepShell
              title="Which equation should we use?"
              subtitle="The Mifflin-St Jeor formula uses a different constant for each. It's about body composition, not identity."
            >
              <OptionList options={SEX_OPTIONS} value={sex} onChange={setSex} />
            </StepShell>
          )}

          {step === 1 && (
            <StepShell
              title="When were you born?"
              subtitle="Metabolic rate falls gradually with age, so the date matters more than you'd think."
            >
              <View style={styles.dateRow}>
                <View style={styles.dateDay}>
                  <TextField
                    label="Day"
                    value={birthDay}
                    onChangeText={setBirthDay}
                    keyboardType="number-pad"
                    maxLength={2}
                    placeholder="20"
                  />
                </View>
                <View style={styles.dateDay}>
                  <TextField
                    label="Month"
                    value={birthMonth}
                    onChangeText={setBirthMonth}
                    keyboardType="number-pad"
                    maxLength={2}
                    placeholder="05"
                  />
                </View>
                <View style={styles.dateYear}>
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
            </StepShell>
          )}

          {step === 2 && (
            <StepShell title="How tall are you?" subtitle="In centimetres.">
              <TextField
                label="Height"
                value={heightCm}
                onChangeText={setHeightCm}
                keyboardType="decimal-pad"
                placeholder="180"
                hint="Between 100 and 250 cm"
              />
            </StepShell>
          )}

          {step === 3 && (
            <StepShell
              title="What do you weigh?"
              subtitle="You'll log this again over time — the trend is what matters, not any single morning."
            >
              <TextField
                label="Weight"
                value={weightKg}
                onChangeText={setWeightKg}
                keyboardType="decimal-pad"
                placeholder="80"
                hint="In kilograms"
              />
            </StepShell>
          )}

          {step === 4 && (
            <StepShell
              title="How active are you, and what are you aiming for?"
              subtitle="Be honest about activity — overestimating here is the most common reason a target comes out too high."
            >
              <Text style={styles.groupLabel}>Activity</Text>
              <OptionList options={ACTIVITY_OPTIONS} value={activity} onChange={setActivity} />
              <Text style={[styles.groupLabel, styles.groupSpacing]}>Goal</Text>
              <OptionList options={GOAL_OPTIONS} value={goal} onChange={setGoal} />
            </StepShell>
          )}

          {error && (
            <View style={styles.errorBox} accessibilityRole="alert">
              <Text style={styles.errorText}>{error}</Text>
            </View>
          )}

          <View style={styles.actions}>
            <Button
              label={step === STEP_COUNT - 1 ? 'See my targets' : 'Continue'}
              disabled={!canAdvance}
              loading={submitting}
              onPress={() => {
                if (step === STEP_COUNT - 1) void handleFinish();
                else setStep(step + 1);
              }}
            />
            {step > 0 && (
              <Pressable
                onPress={() => setStep(step - 1)}
                accessibilityRole="button"
                style={styles.back}
              >
                <Text style={styles.backLabel}>Back</Text>
              </Pressable>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function StepShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.step}>
      <Text style={text.title}>{title}</Text>
      <Text style={[text.bodyMuted, styles.subtitle]}>{subtitle}</Text>
      {children}
    </View>
  );
}

function ProgressDots({ total, current }: { total: number; current: number }) {
  return (
    <View
      style={styles.dots}
      accessibilityRole="progressbar"
      accessibilityLabel={`Step ${current + 1} of ${total}`}
    >
      {Array.from({ length: total }, (_, index) => (
        <View
          key={index}
          style={[
            styles.dot,
            index === current && styles.dotCurrent,
            index < current && styles.dotDone,
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { flexGrow: 1, paddingBottom: space.xxl },
  dots: {
    flexDirection: 'row',
    gap: space.xs,
    marginBottom: space.xl,
  },
  dot: {
    flex: 1,
    height: 3,
    borderRadius: radius.pill,
    backgroundColor: color.inkWash,
  },
  dotDone: { backgroundColor: color.clay, opacity: 0.45 },
  dotCurrent: { backgroundColor: color.clay },
  step: { gap: space.md },
  subtitle: { marginBottom: space.lg },
  groupLabel: { ...text.overline, color: color.inkMuted },
  groupSpacing: { marginTop: space.lg },
  dateRow: { flexDirection: 'row', gap: space.md },
  dateDay: { flex: 1 },
  dateYear: { flex: 1.4 },
  errorBox: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.clayDeep,
  },
  errorText: { ...text.body, fontSize: 14 },
  actions: { marginTop: space.xxl, gap: space.md },
  back: { alignSelf: 'center', padding: space.sm },
  backLabel: { ...text.label, color: color.inkMuted },
});
