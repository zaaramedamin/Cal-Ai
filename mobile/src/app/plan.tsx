/**
 * "Your personalised plan" — the payoff screen after onboarding.
 *
 * Everything numeric here is read back from the server rather than recomputed
 * on the client. The calorie target and macro split are produced by one tested
 * module (`backend/app/nutrition/targets.py`), and a second implementation in
 * TypeScript would be a second thing to keep correct — and the one that drifts.
 *
 * **What is calculated and what is drawn.** The endpoints of the projection are
 * real: today's weight is what the user entered, the target is what they chose,
 * and the date comes from a rate this screen states out loud. The curve between
 * them is a shape, and the screen says so rather than implying a forecast. The
 * warnings the targets module produces are shown here too — the moment to tell
 * someone their target was floored at 1500 kcal is when they first see it, not
 * buried in a settings screen.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { apiErrorMessage } from '@/api/errors';
import { type ProfileWithTargets, getProfile } from '@/api/profile';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { ProjectionChart } from '@/components/projection-chart';
import { Screen } from '@/components/screen';
import { useLanguage } from '@/i18n';
import { HOME } from '@/routes';
import { color, radius, space } from '@/theme/tokens';
import { fontFamily, text } from '@/theme/typography';

/**
 * Weekly rate used to date the projection.
 *
 * 0.75% of bodyweight a week is a conservative middle of the range the
 * literature supports for fat loss without disproportionate lean-mass loss. It
 * is stated on screen, because a projected date whose assumption is hidden is
 * indistinguishable from a made-up one.
 */
const WEEKLY_RATE_FRACTION = 0.0075;

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; data: ProfileWithTargets }
  | { kind: 'error'; message: string };

export default function PlanScreen() {
  const router = useRouter();
  // `language` as well as `t`: the projected date is formatted by the platform,
  // and it has to follow the app's language rather than the device's.
  const { t, language } = useLanguage();
  const [state, setState] = useState<State>({ kind: 'loading' });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getProfile();
        if (!cancelled) setState({ kind: 'ready', data });
      } catch (caught) {
        if (cancelled) return;
        setState({
          kind: 'error',
          message: apiErrorMessage(t, caught, 'plan.loadFailed'),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [t]);

  if (state.kind === 'loading') {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={text.bodyMuted}>{t('plan.building')}</Text>
        </View>
      </Screen>
    );
  }

  if (state.kind === 'error') {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={text.title}>{t('plan.cantLoad')}</Text>
          <Text style={[text.bodyMuted, styles.errorBody]}>{state.message}</Text>
          <Button label={t('plan.toDashboard')} onPress={() => router.replace(HOME)} />
        </View>
      </Screen>
    );
  }

  const { profile, current_weight_kg: current, targets } = state.data;
  const target = profile.target_weight_kg;
  const hasJourney = target !== null && Math.abs(target - current) > 0.5;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.eyebrow}>{t('plan.eyebrow')}</Text>

        {hasJourney ? (
          <>
            <Text style={styles.headline}>
              {target < current ? t('plan.headlineLose') : t('plan.headlineGain')}{' '}
              <Text style={styles.headlineAccent}>{Math.round(target)} kg</Text>{' '}
              {t('plan.headlineBy')}{' '}
              <Text style={styles.headlineAccent}>{projectedDate(current, target, language)}</Text>
            </Text>

            <Card style={styles.chartCard}>
              <ProjectionChart
                startValue={current}
                endValue={target}
                unit="kg"
                endLabel={projectedDate(current, target, language)}
              />
            </Card>

            <View style={styles.disclaimer}>
              <Ionicons name="information-circle-outline" size={15} color={color.inkMuted} />
              <Text style={styles.disclaimerText}>
                {t('plan.disclaimer', { percent: (WEEKLY_RATE_FRACTION * 100).toFixed(2) })}
              </Text>
            </View>
          </>
        ) : (
          <Text style={styles.headline}>
            {t('plan.holdingAt')}{' '}
            <Text style={styles.headlineAccent}>{Math.round(current)} kg</Text>
          </Text>
        )}

        <Text style={styles.sectionTitle}>{t('plan.dailyTargets')}</Text>

        <Card style={styles.calorieCard}>
          <View>
            <Text style={styles.calorieValue}>{targets.calories.toLocaleString()}</Text>
            <Text style={styles.calorieUnit}>{t('plan.kcalPerDay')}</Text>
          </View>
          <Ionicons name="flame" size={30} color={color.flame} />
        </Card>

        <View style={styles.macroRow}>
          <MacroCard
            label={t('common.protein')}
            grams={targets.macros.protein_g}
            tint={color.protein}
            ink={color.proteinText}
          />
          <MacroCard
            label={t('common.carbs')}
            grams={targets.macros.carbs_g}
            tint={color.carbs}
            ink={color.carbsText}
          />
          <MacroCard
            label={t('common.fat')}
            grams={targets.macros.fat_g}
            tint={color.fat}
            ink={color.fatText}
          />
        </View>

        {targets.warnings.length > 0 && (
          // Shown at full strength on the screen where the plan is accepted. A
          // floored target or an aggressive rate is exactly the kind of thing an
          // app is tempted to hide because it dulls the moment.
          <View style={styles.warnings}>
            {targets.warnings.map((warning) => (
              <View key={warning} style={styles.warningRow}>
                <Ionicons name="alert-circle-outline" size={16} color={color.warningText} />
                <Text style={styles.warningText}>{warning}</Text>
              </View>
            ))}
          </View>
        )}

        <Text style={styles.sectionTitle}>{t('plan.howReached')}</Text>
        <Card>
          {/* The derivation the server returns, shown rather than summarised.
              A calorie target is a claim about someone's body; being able to
              follow it step by step is what separates this from an oracle. */}
          {targets.derivation.map((row, index) => (
            <View
              key={row.label}
              style={[styles.derivationRow, index === 0 && styles.derivationFirst]}
            >
              <View style={styles.derivationText}>
                <Text style={styles.derivationLabel}>{row.label}</Text>
                <Text style={styles.derivationDetail}>{row.detail}</Text>
              </View>
              <Text style={styles.derivationValue}>{row.value}</Text>
            </View>
          ))}
        </Card>

        <Text style={styles.editable}>{t('plan.editable')}</Text>
      </ScrollView>

      <Button label={t('plan.start')} onPress={() => router.replace(HOME)} />
    </Screen>
  );
}

function MacroCard({
  label,
  grams,
  tint,
  ink,
}: {
  label: string;
  grams: number;
  tint: string;
  /** The hue deep enough to read as text on white; see `color.carbsText`. */
  ink: string;
}) {
  return (
    <Card compact style={styles.macroCard}>
      <View style={[styles.macroDot, { backgroundColor: tint }]} />
      <Text style={[styles.macroValue, { color: ink }]}>{Math.round(grams)}g</Text>
      <Text style={styles.macroLabel}>{label}</Text>
    </Card>
  );
}

/**
 * When a steady rate would reach the target.
 *
 * Deliberately simple and deliberately surfaced. A more elaborate model — one
 * accounting for the falling TDEE that comes with falling weight — would be
 * more accurate in form and no more honest, because the dominant error here is
 * that people do not adhere perfectly, which no formula captures.
 */
function projectedDate(currentKg: number, targetKg: number, locale: string): string {
  const perWeek = currentKg * WEEKLY_RATE_FRACTION;
  const weeks = perWeek > 0 ? Math.abs(targetKg - currentKg) / perWeek : 0;
  const date = new Date();
  date.setDate(date.getDate() + Math.round(weeks * 7));
  // The app's language, not `undefined`. `undefined` means the device locale,
  // which is a different thing the moment somebody sets the app to French on an
  // English phone — and this date sits inside a French sentence.
  return date.toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' });
}

const styles = StyleSheet.create({
  scroll: { paddingBottom: space.lg, gap: space.md },
  centered: { flex: 1, justifyContent: 'center', gap: space.md },
  errorBody: { marginBottom: space.lg },

  eyebrow: { ...text.overline },
  headline: {
    fontFamily: fontFamily.extraBold,
    fontSize: 28,
    lineHeight: 34,
    letterSpacing: -0.6,
    color: color.ink,
  },
  // The action colour, which is the brand's. It was the fat macro's blue — the
  // one screen where a key number wore a macro's colour without being one.
  headlineAccent: { color: color.accent },

  chartCard: { paddingTop: space.xl, paddingBottom: space.lg },
  disclaimer: { flexDirection: 'row', gap: space.sm, paddingHorizontal: space.xs },
  disclaimerText: { ...text.bodyMuted, fontSize: 11, flex: 1, lineHeight: 16 },

  sectionTitle: { ...text.heading, marginTop: space.lg },

  calorieCard: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  calorieValue: {
    fontFamily: fontFamily.extraBold,
    fontSize: 40,
    letterSpacing: -1,
    color: color.ink,
  },
  calorieUnit: { ...text.bodyMuted, fontSize: 13 },

  macroRow: { flexDirection: 'row', gap: space.md },
  macroCard: { flex: 1, gap: space.xs },
  macroDot: { width: 8, height: 8, borderRadius: radius.pill },
  macroValue: { fontFamily: fontFamily.extraBold, fontSize: 20 },
  macroLabel: { ...text.bodyMuted, fontSize: 12 },

  warnings: { gap: space.sm },
  warningRow: {
    flexDirection: 'row',
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.warningTint,
  },
  warningText: { ...text.body, fontSize: 13, flex: 1, lineHeight: 18 },

  derivationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    paddingVertical: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.hairline,
  },
  derivationFirst: { borderTopWidth: 0, paddingTop: 0 },
  derivationText: { flex: 1, gap: 2 },
  derivationLabel: { ...text.label, fontSize: 14 },
  derivationDetail: { ...text.bodyMuted, fontSize: 12 },
  derivationValue: { ...text.numeric, fontSize: 15 },

  editable: { ...text.bodyMuted, fontSize: 12, marginTop: space.sm },
});
