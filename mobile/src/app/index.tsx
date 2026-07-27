/**
 * Home — your daily targets and how they were worked out.
 *
 * The derivation is rendered from the server's `derivation` list rather than
 * described here. Users trust a number they can follow, and an explanation
 * written in the UI would drift away from the calculation that produced it the
 * first time a constant changed.
 */

import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { type ProfileWithTargets, getProfile } from '@/api/profile';
import { useAuth } from '@/auth/context';
import { Button } from '@/components/button';
import { MacroBar } from '@/components/macro-bar';
import { Screen } from '@/components/screen';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; data: ProfileWithTargets }
  | { kind: 'error'; message: string };

export default function HomeScreen() {
  const router = useRouter();
  const { signOut } = useAuth();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [showWorking, setShowWorking] = useState(false);

  // Refetch whenever the screen regains focus, so returning from onboarding or
  // from a weight update shows current numbers without a manual refresh.
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;

      (async () => {
        try {
          const data = await getProfile();
          if (!cancelled) setState({ kind: 'ready', data });
        } catch (error) {
          if (cancelled) return;
          // 404 means "no profile yet", which is not an error — it is a new
          // account that has not onboarded.
          if (error instanceof ApiError && error.status === 404) {
            router.replace('/onboarding');
            return;
          }
          setState({
            kind: 'error',
            message: error instanceof ApiError ? error.userMessage : 'Could not load your targets.',
          });
        }
      })();

      return () => {
        cancelled = true;
      };
    }, [router]),
  );

  if (state.kind === 'loading') {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={text.bodyMuted}>Loading your targets…</Text>
        </View>
      </Screen>
    );
  }

  if (state.kind === 'error') {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={text.title}>Can&apos;t load your targets</Text>
          <Text style={[text.bodyMuted, styles.errorBody]}>{state.message}</Text>
          <Button label="Sign out" onPress={() => void signOut()} />
        </View>
      </Screen>
    );
  }

  const { targets, current_weight_kg: weight } = state.data;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={text.overline}>Daily target</Text>

        <View style={styles.heroBlock}>
          <Text style={text.hero}>{targets.calories.toLocaleString()}</Text>
          <Text style={text.overline}>kcal per day</Text>
        </View>

        <MacroBar macros={targets.macros} scale="hero" showLegend />

        <View style={styles.statRow}>
          <Stat label="Rest" value={`${targets.bmr.toLocaleString()}`} unit="kcal" />
          <Stat label="Burn" value={`${targets.tdee.toLocaleString()}`} unit="kcal" />
          <Stat label="Weight" value={`${weight}`} unit="kg" />
        </View>

        {targets.warnings.map((warning) => (
          <View key={warning} style={styles.warning} accessibilityRole="alert">
            <Text style={styles.warningText}>{warning}</Text>
          </View>
        ))}

        <Pressable
          onPress={() => setShowWorking((open) => !open)}
          accessibilityRole="button"
          accessibilityState={{ expanded: showWorking }}
          style={styles.disclosure}
        >
          <Text style={styles.disclosureLabel}>
            {showWorking ? 'Hide the working' : 'How was this calculated?'}
          </Text>
        </Pressable>

        {showWorking && (
          <View style={styles.working}>
            {targets.derivation.map((step) => (
              <View key={step.label} style={styles.step}>
                <View style={styles.stepHeader}>
                  <Text style={text.label}>{step.label}</Text>
                  <Text style={styles.stepValue}>{step.value}</Text>
                </View>
                <Text style={styles.stepDetail}>{step.detail}</Text>
              </View>
            ))}
          </View>
        )}

        <View style={styles.nextUp}>
          <Text style={text.overline}>Next</Text>
          <Text style={styles.stepDetail}>
            Phase 3 adds the food database, so you can search real USDA foods and log them
            against these targets.
          </Text>
        </View>

        <View style={styles.actions}>
          <Button label="Edit my details" onPress={() => router.push('/onboarding')} />
          <Pressable
            onPress={() => void signOut()}
            accessibilityRole="button"
            style={styles.signOut}
          >
            <Text style={styles.signOutLabel}>Sign out</Text>
          </Pressable>
        </View>
      </ScrollView>
    </Screen>
  );
}

function Stat({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <View style={styles.stat}>
      <Text style={text.overline}>{label}</Text>
      <Text style={text.heading}>{value}</Text>
      <Text style={styles.statUnit}>{unit}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: space.xxl },
  centered: { flex: 1, justifyContent: 'center', gap: space.md },
  errorBody: { marginBottom: space.lg },
  heroBlock: { marginTop: space.xs, marginBottom: space.lg },
  statRow: {
    flexDirection: 'row',
    marginTop: space.xl,
    gap: space.md,
  },
  stat: {
    flex: 1,
    padding: space.md,
    backgroundColor: color.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.hairline,
    borderRadius: radius.md,
    gap: 2,
  },
  statUnit: { ...text.bodyMuted, fontSize: 12 },
  warning: {
    marginTop: space.lg,
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.wheat,
  },
  warningText: { ...text.body, fontSize: 14, lineHeight: 20 },
  disclosure: { marginTop: space.xl, paddingVertical: space.sm },
  disclosureLabel: { ...text.label, color: color.clay },
  working: {
    gap: space.lg,
    padding: space.lg,
    backgroundColor: color.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.hairline,
    borderRadius: radius.lg,
  },
  step: { gap: space.xs },
  stepHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    gap: space.sm,
  },
  stepValue: { ...text.numeric },
  stepDetail: { ...text.bodyMuted, fontSize: 13, lineHeight: 19 },
  nextUp: { marginTop: space.xxl, gap: space.sm },
  actions: { marginTop: space.xl, gap: space.md },
  signOut: { alignSelf: 'center', padding: space.sm },
  signOutLabel: { ...text.label, color: color.inkMuted },
});
