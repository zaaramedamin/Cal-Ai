/**
 * Add a food from its label.
 *
 * **Why this exists.** Most barcodes on a shelf are not in Open Food Facts, and
 * until now a miss was a dead end — the product is in your hand, the numbers are
 * printed on it, and the app had nothing to offer. Two minutes of typing turns
 * that into a food you own.
 *
 * **Blank is not zero.** Optional nutrients left empty are sent as null, so a
 * label that does not state fibre produces a food that does not claim to know
 * its fibre. Defaulting them to 0 would be the same fabrication the importers
 * refuse, made by the user instead of by us — and it would look identical to a
 * measured zero afterwards.
 */

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';

import { apiErrorMessage } from '@/api/errors';
import { type MealSlot, createCustomFood } from '@/api/diary';
import { BackHeader } from '@/components/back-header';
import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

/** Empty means "the label did not say", which is null — never zero. */
function optional(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

function required(value: string): number | null {
  const parsed = optional(value);
  return parsed === null || parsed < 0 ? null : parsed;
}

export default function NewFoodScreen() {
  const router = useRouter();
  const t = useT();
  const params = useLocalSearchParams<{ barcode?: string; day?: string; slot?: MealSlot }>();

  const [name, setName] = useState('');
  const [brand, setBrand] = useState('');
  const [kcal, setKcal] = useState('');
  const [protein, setProtein] = useState('');
  const [carbs, setCarbs] = useState('');
  const [fat, setFat] = useState('');
  const [sugars, setSugars] = useState('');
  const [saturated, setSaturated] = useState('');
  const [fibre, setFibre] = useState('');
  const [sodium, setSodium] = useState('');
  const [serving, setServing] = useState('');

  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const ready =
    name.trim().length > 0 &&
    required(kcal) !== null &&
    required(protein) !== null &&
    required(carbs) !== null &&
    required(fat) !== null;

  async function save() {
    if (!ready || saving) return;
    setSaving(true);
    setError(null);

    try {
      const food = await createCustomFood({
        name: name.trim(),
        brand: brand.trim() || null,
        barcode: params.barcode ?? null,
        kcal: required(kcal)!,
        protein_g: required(protein)!,
        carbs_g: required(carbs)!,
        fat_g: required(fat)!,
        sugars_g: optional(sugars),
        saturated_fat_g: optional(saturated),
        fibre_g: optional(fibre),
        sodium_mg: optional(sodium),
        serving_grams: optional(serving),
      });

      // Straight to the food screen to choose an amount, which is where every
      // other route into the diary ends up. `replace` so Back does not return
      // to a form that has already been submitted.
      router.replace({
        pathname: '/food/[id]',
        params: { id: food.id, day: params.day, slot: params.slot },
      });
    } catch (caught) {
      setError(apiErrorMessage(t, caught, 'auth.somethingWrong'));
      setSaving(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <BackHeader />
          <Text style={text.title}>{t('food.customTitle')}</Text>
          <Text style={[text.bodyMuted, styles.intro]}>{t('food.customIntro')}</Text>

          <View style={styles.fields}>
            <TextField label={t('food.nameLabel')} value={name} onChangeText={setName} />
            <TextField label={t('food.brandLabel')} value={brand} onChangeText={setBrand} />

            <Text style={[text.overline, styles.section]}>{t('food.per100g')}</Text>

            <TextField
              label={`${t('common.kcal')} *`}
              value={kcal}
              onChangeText={setKcal}
              keyboardType="decimal-pad"
            />
            <TextField
              label={`${t('common.protein')} (g) *`}
              value={protein}
              onChangeText={setProtein}
              keyboardType="decimal-pad"
            />
            <TextField
              label={`${t('common.carbs')} (g) *`}
              value={carbs}
              onChangeText={setCarbs}
              keyboardType="decimal-pad"
            />
            <TextField
              label={`${t('common.fat')} (g) *`}
              value={fat}
              onChangeText={setFat}
              keyboardType="decimal-pad"
            />

            <TextField
              label={t('nutrient.sugarsField')}
              value={sugars}
              onChangeText={setSugars}
              keyboardType="decimal-pad"
            />
            <TextField
              label={t('nutrient.saturatesField')}
              value={saturated}
              onChangeText={setSaturated}
              keyboardType="decimal-pad"
            />
            <TextField
              label={t('nutrient.fibreField')}
              value={fibre}
              onChangeText={setFibre}
              keyboardType="decimal-pad"
            />
            <TextField
              label={t('nutrient.sodiumField')}
              value={sodium}
              onChangeText={setSodium}
              keyboardType="decimal-pad"
            />

            <TextField
              label={t('food.servingLabel')}
              value={serving}
              onChangeText={setServing}
              keyboardType="decimal-pad"
            />
          </View>

          {error && (
            <View style={styles.callout} accessibilityRole="alert">
              <Text style={styles.calloutText}>{error}</Text>
            </View>
          )}

          <View style={styles.actions}>
            <Button
              label={t('food.saveFood')}
              onPress={() => void save()}
              loading={saving}
              disabled={!ready}
            />
            <Text style={styles.note}>{t('food.privateNote')}</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { flexGrow: 1, paddingBottom: space.xxl },
  intro: { marginTop: space.sm, lineHeight: 21 },
  fields: { marginTop: space.xl, gap: space.lg },
  section: { marginTop: space.md, color: color.inkMuted },
  callout: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.dangerTint,
    borderLeftWidth: 3,
    borderLeftColor: color.danger,
  },
  calloutText: { ...text.body, fontSize: 14 },
  actions: { marginTop: space.xl, gap: space.md },
  note: { ...text.bodyMuted, fontSize: 11, lineHeight: 16, textAlign: 'center' },
});
