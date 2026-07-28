/**
 * Browse the curated catalogue.
 *
 * The screen this project needed and did not have. USDA holds 300,000 entries
 * filed as taxonomy, and a person wanting to log a chicken breast should not
 * have to read a classification scheme. This is a menu: thirty-odd foods, short
 * names, an image each, grouped into sections you can scan without reading.
 *
 * Tapping a food opens a portion sheet rather than navigating. Logging breakfast
 * is a repeated act, and a screen transition each way turns four taps into six
 * plus two animations you have to wait through.
 */

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { ApiError } from '@/api/client';
import {
  type CatalogueFood,
  type CatalogueSection,
  getCatalogue,
  logCatalogueFood,
} from '@/api/catalogue';
import { MEAL_LABELS, type MealSlot } from '@/api/diary';
import { AmountStepper } from '@/components/amount-stepper';
import { Button } from '@/components/button';
import { FoodThumb } from '@/components/food-thumb';
import { EnterUp, PressableScale } from '@/components/motion';
import { Screen } from '@/components/screen';
import { draftActions, itemFromFood, useDraftMeal } from '@/features/meals/draft-store';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; sections: CatalogueSection[]; total: number }
  | { kind: 'error'; message: string };

export default function CatalogueScreen() {
  const router = useRouter();
  const { slot, day, mode } = useLocalSearchParams<{
    slot?: MealSlot;
    day?: string;
    /** 'meal' adds the chosen food to the meal draft instead of the diary. */
    mode?: string;
  }>();
  const buildingMeal = mode === 'meal';
  const draft = useDraftMeal();

  const [state, setState] = useState<State>({ kind: 'loading' });
  const [chosen, setChosen] = useState<CatalogueFood | null>(null);

  const load = useCallback(async () => {
    setState({ kind: 'loading' });
    try {
      const response = await getCatalogue();
      setState({ kind: 'ready', sections: response.sections, total: response.total });
    } catch (caught) {
      setState({
        kind: 'error',
        message: caught instanceof ApiError ? caught.userMessage : 'Could not load the catalogue.',
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={text.overline}>
          {buildingMeal ? 'Add ingredient' : slot ? `Add to ${MEAL_LABELS[slot]}` : 'Ingredients'}
        </Text>
        <Pressable onPress={() => router.back()} accessibilityRole="button" style={styles.cancel}>
          <Text style={styles.cancelLabel}>{buildingMeal ? 'Done' : 'Cancel'}</Text>
        </Pressable>
      </View>

      {state.kind === 'loading' && (
        <View style={styles.centered}>
          <ActivityIndicator color={color.accent} />
        </View>
      )}

      {state.kind === 'error' && (
        <View style={styles.centered}>
          <Text style={text.title}>Couldn&apos;t load</Text>
          <Text style={[text.bodyMuted, styles.centeredBody]}>{state.message}</Text>
          <Button label="Try again" onPress={() => void load()} variant="secondary" />
        </View>
      )}

      {state.kind === 'ready' && state.total === 0 && <EmptyCatalogue />}

      {state.kind === 'ready' && state.total > 0 && (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
          {state.sections.map((section, index) => (
            <EnterUp key={section.category} index={index}>
              <View style={styles.section}>
                <Text style={styles.sectionHeading}>{section.category}</Text>
                <View style={styles.grid}>
                  {section.foods.map((food) => (
                    <FoodTile
                      key={food.slug}
                      food={food}
                      inMeal={buildingMeal && draft.items.some((row) => row.slug === food.slug)}
                      onPress={() => setChosen(food)}
                    />
                  ))}
                </View>
              </View>
            </EnterUp>
          ))}

          <Text style={styles.footnote}>
            {state.total} ingredients. Every number is verified against USDA FoodData Central.
          </Text>
        </ScrollView>
      )}

      {/* The meal draft rides along the bottom while you pick, so you can see
          what you have added without leaving the list. */}
      {buildingMeal && draft.items.length > 0 && (
        <Pressable
          onPress={() => router.back()}
          accessibilityRole="button"
          style={styles.draftBar}
        >
          <Text style={styles.draftCount}>
            {draft.items.length} {draft.items.length === 1 ? 'ingredient' : 'ingredients'}
          </Text>
          <Text style={styles.draftAction}>Back to meal →</Text>
        </Pressable>
      )}

      {chosen && (
        <PortionSheet
          food={chosen}
          slot={slot ?? 'snack'}
          day={day}
          buildingMeal={buildingMeal}
          onClose={() => setChosen(null)}
          onLogged={() => {
            setChosen(null);
            router.back();
          }}
          onAdded={() => setChosen(null)}
        />
      )}
    </Screen>
  );
}

function FoodTile({
  food,
  inMeal,
  onPress,
}: {
  food: CatalogueFood;
  inMeal: boolean;
  onPress: () => void;
}) {
  return (
    <PressableScale
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={food.name_en}
      style={[styles.tile, inMeal && styles.tileOn]}
    >
      <FoodThumb emoji={food.emoji} photo={food.photo} size={44} />
      <Text style={styles.tileName} numberOfLines={2}>
        {food.name_en}
      </Text>
      <Text style={styles.tileKcal}>{Math.round(food.kcal)} kcal/100g</Text>
      {inMeal && <View style={styles.tileTick} />}
    </PressableScale>
  );
}

/**
 * What the screen shows before the catalogue has been seeded.
 *
 * Named honestly rather than shown as a spinner or an empty grid. The catalogue
 * is filled by a command that needs a USDA key, and "nothing here" with no
 * explanation is indistinguishable from a broken screen.
 */
function EmptyCatalogue() {
  return (
    <View style={styles.centered}>
      <Text style={styles.emptyGlyph}>🥗</Text>
      <Text style={text.title}>The catalogue is empty</Text>
      <Text style={[text.bodyMuted, styles.centeredBody]}>
        Its numbers come from USDA FoodData Central, and filling it needs an API key. Run{' '}
        <Text style={styles.code}>python -m app.cli seed-catalogue</Text> on the server once{' '}
        <Text style={styles.code}>USDA_API_KEY</Text> is set.
      </Text>
    </View>
  );
}

/**
 * Pick an amount, then log it — or add it to the meal being built.
 *
 * A modal rather than a route because it is a decision about the thing you just
 * tapped, not a new place. Coming back to the list afterwards should feel like
 * the sheet closing, not like navigating backwards.
 */
function PortionSheet({
  food,
  slot,
  day,
  buildingMeal,
  onClose,
  onLogged,
  onAdded,
}: {
  food: CatalogueFood;
  slot: MealSlot;
  day?: string;
  buildingMeal: boolean;
  onClose: () => void;
  onLogged: () => void;
  onAdded: () => void;
}) {
  const preferred = food.portions.find((portion) => portion.is_default) ?? food.portions[0];
  const [amount, setAmount] = useState(preferred?.amount ?? 1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const grams = amount * food.grams_per_unit;
  const kcal = Math.round((food.kcal * grams) / 100);

  const submit = async () => {
    if (buildingMeal) {
      draftActions.addItem(itemFromFood(food, amount));
      onAdded();
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await logCatalogueFood({ slug: food.slug, amount, mealSlot: slot, day });
      onLogged();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.userMessage : 'Could not log that.');
      setBusy(false);
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityRole="button" />
      <View style={styles.sheet}>
        <View style={styles.sheetHandle} />

        <View style={styles.sheetHead}>
          <FoodThumb emoji={food.emoji} photo={food.photo} size={52} />
          <View style={styles.sheetTitles}>
            <Text style={text.title}>{food.name_en}</Text>
            <Text style={text.bodyMuted}>{food.name_fr}</Text>
          </View>
        </View>

        <AmountStepper food={food} amount={amount} onChange={setAmount} />

        <View style={styles.summary}>
          <Text style={styles.summaryKcal}>{kcal}</Text>
          <Text style={styles.summaryUnit}>kcal</Text>
          <View style={styles.summarySpacer} />
          <Macro label="P" value={(food.protein_g * grams) / 100} tint={color.proteinTint} />
          <Macro label="C" value={(food.carbs_g * grams) / 100} tint={color.carbsTint} />
          <Macro label="F" value={(food.fat_g * grams) / 100} tint={color.fatTint} />
        </View>

        {error && (
          <Text style={styles.error} accessibilityRole="alert">
            {error}
          </Text>
        )}

        <Button
          label={buildingMeal ? 'Add to meal' : `Log to ${MEAL_LABELS[slot]}`}
          onPress={() => void submit()}
          loading={busy}
        />
      </View>
    </Modal>
  );
}

function Macro({ label, value, tint }: { label: string; value: number; tint: string }) {
  return (
    <View style={[styles.macro, { backgroundColor: tint }]}>
      <Text style={styles.macroLabel}>{label}</Text>
      <Text style={styles.macroValue}>{Math.round(value)}g</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.md,
  },
  cancel: { minHeight: HIT_SLOP_MIN, justifyContent: 'center', paddingLeft: space.md },
  cancelLabel: { ...text.label, color: color.accent },

  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.md,
    paddingBottom: space.xxl,
  },
  centeredBody: { textAlign: 'center', lineHeight: 21 },
  emptyGlyph: { fontSize: 44 },
  code: { ...text.bodyMuted, fontFamily: 'monospace', color: color.ink },

  scroll: { paddingBottom: space.xxxl, gap: space.xl },
  section: { gap: space.sm },
  sectionHeading: { ...text.overline, color: color.inkMuted },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  tile: {
    width: '31.5%',
    aspectRatio: 0.92,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    paddingHorizontal: space.xs,
    paddingVertical: space.sm,
    borderRadius: radius.md,
    backgroundColor: color.surface,
  },
  tileOn: { backgroundColor: color.accentTint },
  tileName: { ...text.label, fontSize: 12, textAlign: 'center', lineHeight: 14 },
  tileKcal: { ...text.bodyMuted, fontSize: 10 },
  tileTick: {
    position: 'absolute',
    top: space.sm,
    right: space.sm,
    width: 8,
    height: 8,
    borderRadius: radius.pill,
    backgroundColor: color.accent,
  },
  footnote: { ...text.bodyMuted, fontSize: 11, textAlign: 'center' },

  draftBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.md,
    backgroundColor: color.ink,
  },
  draftCount: { ...text.label, color: color.onDark },
  draftAction: { ...text.label, color: color.onDark, opacity: 0.75 },

  backdrop: { flex: 1, backgroundColor: 'rgba(11, 16, 32, 0.45)' },
  sheet: {
    backgroundColor: color.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: space.xl,
    paddingBottom: space.xxl,
    gap: space.lg,
  },
  sheetHandle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: color.hairline,
  },
  sheetHead: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  sheetTitles: { flex: 1, gap: 2 },

  summary: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  summaryKcal: { ...text.numeric, fontSize: 30 },
  summaryUnit: { ...text.bodyMuted, marginLeft: 2 },
  summarySpacer: { flex: 1 },
  macro: {
    alignItems: 'center',
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
    borderRadius: radius.sm,
    minWidth: 44,
  },
  macroLabel: { ...text.overline, fontSize: 9 },
  macroValue: { ...text.label, fontSize: 13 },

  error: { ...text.bodyMuted, color: color.danger, fontSize: 13 },
});
