/**
 * Food detail and portion selector.
 *
 * The last screen before something lands in the diary, so it has to make the
 * quantity unambiguous. Portions are offered as chips with their gram weight
 * shown — "1 medium (118 g)" — because the label alone hides the number the
 * calculation actually uses, and a user who thinks a medium banana is 150 g
 * should be able to see the difference rather than discover it later.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { apiErrorMessage } from '@/api/errors';
import {
  type Food,
  MEAL_SLOTS,
  type MealSlot,
  getFood,
  logFood,
} from '@/api/diary';
import { BackHeader } from '@/components/back-header';
import { Button } from '@/components/button';
import { MacroBar } from '@/components/macro-bar';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { parseDecimal } from '@/lib/units';
import { HOME } from '@/routes';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';
import { submitFood } from '@/api/review';
import { useT } from '@/i18n';
import type { StringKey } from '@/i18n/strings';

/** How each source is named to the user. */
const SOURCE_LABELS: Record<string, StringKey> = {
  usda: 'food.sourceUsda',
  off: 'food.sourceOffName',
  innta: 'food.sourceInnta',
  ciqual: 'food.sourceCiqual',
  user: 'food.sourceYou',
  ai_estimate: 'food.sourceAi',
};

/**
 * What kind of claim each source is making.
 *
 * Only the ones that need qualifying carry a line. USDA does not: it is the
 * baseline this app is built on, and putting a caveat under everything trains
 * people to read none of them.
 */
const SOURCE_CAVEATS: Record<string, StringKey | undefined> = {
  off: 'food.sourceOff',
  user: 'food.sourceUser',
  ai_estimate: 'food.sourceEstimate',
};

export default function FoodDetailScreen() {
  const router = useRouter();
  const t = useT();
  const { id, slot, day } = useLocalSearchParams<{
    id: string;
    slot?: MealSlot;
    day?: string;
  }>();

  const [food, setFood] = useState<Food | null>(null);
  const [grams, setGrams] = useState('100');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // The + button infers a slot from the time of day; this is where the user
  // corrects it. State starts from the param and the chips below override.
  const [chosenSlot, setChosenSlot] = useState<MealSlot>(slot ?? 'snack');
  const [sharing, setSharing] = useState(false);
  const [shared, setShared] = useState(false);

  async function share() {
    if (!food || sharing || shared) return;
    setSharing(true);
    try {
      await submitFood(food.id);
      setShared(true);
    } catch (caught) {
      setError(apiErrorMessage(t, caught, 'auth.somethingWrong'));
    } finally {
      setSharing(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await getFood(id);
        if (cancelled) return;
        setFood(loaded);
        // Start at the food's default portion when it has one; 100 g otherwise.
        const preferred = loaded.portions.find((portion) => portion.is_default);
        if (preferred) setGrams(String(Math.round(preferred.grams)));
      } catch (caught) {
        if (!cancelled) {
          setError(apiErrorMessage(t, caught, 'food.loadFailed'));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // parseDecimal, not Number: a French keypad types "12,5".
  const quantity = parseDecimal(grams) ?? Number.NaN;
  const valid = Number.isFinite(quantity) && quantity > 0;

  // Scaled live from the per-100 g values, so the numbers on screen are always
  // the numbers that will be logged.
  //
  // **An invalid quantity scales to zero, it does not return null.** This used
  // to be `if (!food || !valid) return null`, and the guard below treats a null
  // `scaled` as "still loading" — so clearing the amount field emptied the whole
  // screen and replaced it with the word "Loading…". Deleting three characters
  // made the food you were looking at disappear.
  //
  // Zero is also the honest number to show: you are about to log nothing.
  const scaled = useMemo(() => {
    if (!food) return null;
    const factor = valid ? quantity / 100 : 0;
    return {
      kcal: food.kcal * factor,
      protein_g: food.protein_g * factor,
      carbs_g: food.carbs_g * factor,
      fat_g: food.fat_g * factor,
      fibre_g: food.fibre_g === null ? null : food.fibre_g * factor,
      sugars_g: food.sugars_g === null ? null : food.sugars_g * factor,
      saturated_fat_g:
        food.saturated_fat_g === null ? null : food.saturated_fat_g * factor,
      sodium_mg: food.sodium_mg === null ? null : food.sodium_mg * factor,
    };
  }, [food, quantity, valid]);

  async function handleLog() {
    if (!valid || !food) return;
    setSaving(true);
    setError(null);
    try {
      await logFood({
        foodId: food.id,
        mealSlot: chosenSlot,
        quantityGrams: quantity,
        localDate: day || undefined,
      });
      // Back to the dashboard, which refetches on focus. dismissAll rather than
      // back, so the search screen is not left behind on the stack.
      router.dismissAll();
      router.replace(HOME);
    } catch (caught) {
      setError(apiErrorMessage(t, caught, 'food.logFailed'));
    } finally {
      setSaving(false);
    }
  }

  if (error && !food) {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={text.title}>{t('food.cantLoad')}</Text>
          <Text style={[text.bodyMuted, styles.errorBody]}>{error}</Text>
          <Button label={t('common.back')} onPress={() => router.back()} />
        </View>
      </Screen>
    );
  }

  if (!food || !scaled) {
    return (
      <Screen>
        <BackHeader />
        {/* Centred properly: `flex: 1` on the wrapper plus `justifyContent`,
            rather than relying on whatever height the content happened to have.
            The spinner used to sit just under the status bar. */}
        <View style={styles.loading}>
          <ActivityIndicator color={color.ink} />
          <Text style={[text.bodyMuted, styles.loadingLabel]}>{t('common.loading')}</Text>
        </View>
      </Screen>
    );
  }

  const unit = food.is_liquid ? 'ml' : 'g';

  return (
    <Screen>
      {/* Every screen hides the native header, and this one had no way back but
          the system gesture — which Android users find and iOS users often
          don't. */}
      <BackHeader title={t('catalogue.addTo', { slot: t(`slot.${chosenSlot}`) })} />
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        automaticallyAdjustKeyboardInsets
        showsVerticalScrollIndicator={false}
      >
        <Text style={text.title}>{food.name}</Text>
        {food.brand && <Text style={[text.bodyMuted, styles.brand]}>{food.brand}</Text>}

        {/* A withdrawn food is still reachable — a diary entry logged before the
            withdrawal has to render — so the screen says what happened instead
            of looking normal. `withdrawn_reason` is the admin's words. */}
        {food.withdrawn_reason !== null && (
          <View style={styles.withdrawn} accessibilityRole="alert">
            <View style={styles.withdrawnHead}>
              <Ionicons name="alert-circle" size={16} color={color.danger} />
              <Text style={styles.withdrawnTitle}>{t('food.withdrawn')}</Text>
            </View>
            <Text style={styles.withdrawnBody}>{t('food.withdrawnBody')}</Text>
            <Text style={styles.withdrawnBody}>{food.withdrawn_reason}</Text>
          </View>
        )}

        <View style={styles.heroBlock}>
          <Text style={text.hero}>{Math.round(scaled.kcal).toLocaleString()}</Text>
          <Text style={text.overline}>{t('food.kcalFor', { amount: quantity, unit })}</Text>
        </View>

        <MacroBar macros={scaled} scale="hero" showLegend />

        <Text style={[text.overline, styles.sectionLabel]}>{t('food.mealSection')}</Text>
        <View style={styles.slotRow}>
          {MEAL_SLOTS.map((option) => {
            const selected = option === chosenSlot;
            return (
              <Pressable
                key={option}
                onPress={() => setChosenSlot(option)}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                style={[styles.slotChip, selected && styles.slotChipSelected]}
              >
                <Text style={[styles.slotChipLabel, selected && styles.slotChipLabelSelected]}>
                  {t(`slot.${option}`)}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Text style={[text.overline, styles.sectionLabel]}>{t('food.quantitySection')}</Text>
        <TextField
          label={t('food.amountIn', { unit })}
          value={grams}
          onChangeText={setGrams}
          keyboardType="decimal-pad"
          error={valid ? null : t('food.amountPositive')}
        />

        {food.portions.length > 0 && (
          <View style={styles.portions}>
            {food.portions.map((portion) => {
              const selected = Math.round(portion.grams) === Math.round(quantity);
              return (
                <Pressable
                  key={portion.id}
                  onPress={() => setGrams(String(Math.round(portion.grams)))}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  style={[styles.portion, selected && styles.portionSelected]}
                >
                  <Text style={[text.label, styles.portionLabel]}>{portion.label}</Text>
                  <Text style={styles.portionGrams}>
                    {Math.round(portion.grams)} {unit}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        )}

        <Text style={[text.overline, styles.sectionLabel]}>{t('nutrient.full')}</Text>
        <View style={styles.table}>
          <NutrientRow label={t('nutrient.protein')} value={scaled.protein_g} unit="g" />
          <NutrientRow label={t('nutrient.carbs')} value={scaled.carbs_g} unit="g" />
          <NutrientRow label={t('nutrient.sugars')} value={scaled.sugars_g} unit="g" indented />
          <NutrientRow label={t('nutrient.fat')} value={scaled.fat_g} unit="g" />
          <NutrientRow
            label={t('nutrient.saturates')}
            value={scaled.saturated_fat_g}
            unit="g"
            indented
          />
          <NutrientRow label={t('nutrient.fibre')} value={scaled.fibre_g} unit="g" />
          <NutrientRow label={t('nutrient.sodium')} value={scaled.sodium_mg} unit="mg" />
        </View>

        {/* Only for a food you wrote that is not already shared. `source` is
            the check rather than a flag on the response: a food from USDA or
            Open Food Facts is not yours to offer, and one already approved has
            nothing to offer. */}
        {food.source === 'user' && (
          <View style={styles.shareBlock}>
            <Text style={text.label}>{t('submit.share')}</Text>
            <Text style={styles.shareBody}>{t('submit.shareBody')}</Text>
            <Button
              label={shared ? t('submit.sent') : t('submit.share')}
              onPress={() => void share()}
              loading={sharing}
              disabled={shared}
            />
          </View>
        )}

        {/* Named, and characterised. "USDA" and "Open Food Facts" are not the
            same kind of claim — one is lab analysis, the other is a volunteer
            reading a label — and a user who can see which is which can weigh
            them differently. Printing a bare source id told them nothing. */}
        <View style={styles.sourceBlock}>
          <Text style={styles.source}>
            {t('food.source')}:{' '}
            {SOURCE_LABELS[food.source] ? t(SOURCE_LABELS[food.source]) : food.source}
            {food.source_id.startsWith('user:') ? '' : ` · ${food.source_id}`}
          </Text>
          {SOURCE_CAVEATS[food.source] && (
            <Text style={styles.sourceCaveat}>{t(SOURCE_CAVEATS[food.source]!)}</Text>
          )}
        </View>

        {/* Reporting sits directly under the source, which is where it belongs:
            the source line is the claim, and this is how you dispute it. Every
            food gets the link, including USDA and Open Food Facts rows — those
            are the ones most worth reporting, because nobody here typed them and
            nobody here has ever checked them. */}
        <Pressable
          onPress={() => router.push({ pathname: '/report/[id]', params: { id: food.id } })}
          accessibilityRole="button"
          style={styles.reportLink}
        >
          <Ionicons name="flag-outline" size={15} color={color.inkMuted} />
          <Text style={styles.reportLabel}>{t('report.link')}</Text>
        </Pressable>
      </ScrollView>

      {/* Pinned below the scroll, not at the end of it. The button is the reason
          this screen exists, and it sat under the whole nutrient table — below
          the fold on every phone, so logging a food meant scrolling past
          information most people never read. */}
      <View style={styles.actions}>
        {error && (
          <View style={styles.callout} accessibilityRole="alert">
            <Text style={styles.calloutText}>{error}</Text>
          </View>
        )}
        <Button
          label={t('food.logAmount', { amount: valid ? quantity : 0, unit })}
          disabled={!valid}
          loading={saving}
          onPress={() => void handleLog()}
        />
      </View>
    </Screen>
  );
}

function NutrientRow({
  label,
  value,
  unit,
  indented,
}: {
  label: string;
  value: number | null;
  unit: string;
  indented?: boolean;
}) {
  return (
    <View style={styles.tableRow}>
      <Text style={[styles.tableLabel, indented && styles.tableLabelIndented]}>{label}</Text>
      {/* An em dash, never 0. Null means this source did not report the
          nutrient, which is a different claim from "there is none of it". */}
      <Text style={styles.tableValue}>
        {value === null ? '—' : `${value.toFixed(1)} ${unit}`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.sm },
  loadingLabel: { marginTop: space.xs },

  reportLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    alignSelf: 'flex-start',
    minHeight: HIT_SLOP_MIN,
    paddingVertical: space.sm,
  },
  reportLabel: { ...text.bodyMuted, fontSize: 13, textDecorationLine: 'underline' },

  withdrawn: {
    marginTop: space.md,
    padding: space.md,
    gap: space.xs,
    borderRadius: radius.md,
    backgroundColor: color.dangerTint,
    borderLeftWidth: 3,
    borderLeftColor: color.danger,
  },
  withdrawnHead: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  withdrawnTitle: { ...text.label, fontSize: 13, color: color.dangerText },
  withdrawnBody: { ...text.body, fontSize: 13, lineHeight: 19 },

  content: { paddingBottom: space.xxl },
  centered: { flex: 1, justifyContent: 'center', gap: space.md },
  errorBody: { marginBottom: space.lg },
  brand: { marginTop: space.xs },
  // The 44pt number needs air on both sides or it crowds the food name
  // above it and the macro bar below.
  heroBlock: { marginTop: space.xl, marginBottom: space.xl },
  sectionLabel: { marginTop: space.xl, marginBottom: space.sm },
  slotRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  slotChip: {
    minHeight: HIT_SLOP_MIN - 8,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
  },
  slotChipSelected: { backgroundColor: color.accent, borderColor: color.accent },
  slotChipLabel: { ...text.label, fontSize: 13 },
  slotChipLabelSelected: { color: color.onDark },
  portions: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md },
  portion: {
    minHeight: HIT_SLOP_MIN,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.md,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
  },
  portionSelected: { borderColor: color.accent, backgroundColor: color.accentTint },
  portionLabel: { fontSize: 13 },
  portionGrams: { ...text.bodyMuted, fontSize: 11 },
  table: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.hairline,
    paddingHorizontal: space.lg,
  },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.hairline,
  },
  tableLabel: { ...text.body, fontSize: 14 },
  tableLabelIndented: { paddingLeft: space.md, color: color.inkMuted, fontSize: 13 },
  tableValue: { ...text.numeric, fontSize: 14 },
  shareBlock: {
    marginTop: space.xl,
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: color.accentTint,
    gap: space.sm,
  },
  shareBody: { ...text.bodyMuted, fontSize: 12, lineHeight: 18 },
  sourceBlock: { marginTop: space.md, gap: space.xs },
  source: { ...text.bodyMuted, fontSize: 11 },
  sourceCaveat: { ...text.bodyMuted, fontSize: 11, lineHeight: 16, fontStyle: 'italic' },
  callout: {
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.dangerTint,
    borderLeftWidth: 3,
    borderLeftColor: color.danger,
  },
  calloutText: { ...text.body, fontSize: 14 },
  actions: {
    gap: space.md,
    paddingTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.hairline,
  },
});
