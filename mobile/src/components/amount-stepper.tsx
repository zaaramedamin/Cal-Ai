/**
 * Choosing how much, in the food's own unit.
 *
 * Two controls, and the split matters. The **portion chips** are the fast path —
 * "2 eggs", "1 verre" — and cover what people actually eat. The **stepper**
 * underneath is the escape hatch for everything else, and it steps by an amount
 * that suits the unit: half an item, 25 ml, 10 g. One universal step would make
 * eggs absurd or milk useless.
 *
 * The gram weight is shown but never editable. It is derived from the amount by
 * the food's own density or item weight, and letting the user type it directly
 * would create two sources of truth that disagree the moment either changes.
 */

import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  type CatalogueFood,
  amountStep,
  formatAmount,
  unitSuffix,
} from '@/api/catalogue';
import { PressableScale } from '@/components/motion';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

interface AmountStepperProps {
  food: CatalogueFood;
  amount: number;
  onChange: (amount: number) => void;
  /** Language for the portion labels. */
  french?: boolean;
}

export function AmountStepper({ food, amount, onChange, french = false }: AmountStepperProps) {
  const step = amountStep(food.unit);
  const suffix = unitSuffix(food.unit);

  const nudge = (delta: number) => {
    // Rounded to the step so repeated taps cannot accumulate floating-point
    // drift into "1.9999999999 eggs".
    const next = Math.round((amount + delta) / step) * step;
    onChange(Math.min(10_000, Math.max(step, Number(next.toFixed(2)))));
  };

  const grams = amount * food.grams_per_unit;

  return (
    <View style={styles.root}>
      <View style={styles.chips}>
        {food.portions.map((portion) => {
          const selected = Math.abs(portion.amount - amount) < 0.001;
          return (
            <PressableScale
              key={portion.label_en}
              onPress={() => onChange(portion.amount)}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              style={[styles.chip, selected && styles.chipOn]}
            >
              <Text style={[styles.chipLabel, selected && styles.chipLabelOn]}>
                {french ? portion.label_fr : portion.label_en}
              </Text>
            </PressableScale>
          );
        })}
      </View>

      <View style={styles.stepper}>
        <Pressable
          onPress={() => nudge(-step)}
          accessibilityRole="button"
          accessibilityLabel="Less"
          style={styles.stepButton}
        >
          <Text style={styles.stepGlyph}>−</Text>
        </Pressable>

        <View style={styles.readout}>
          <Text style={styles.amount}>
            {formatAmount(amount)}
            {suffix ? ` ${suffix}` : ''}
          </Text>
          {/* Only worth showing when it differs from the amount — repeating
              "150 g / 150 g" under a gram food is noise. */}
          {food.unit !== 'g' && (
            <Text style={styles.grams}>≈ {Math.round(grams)} g</Text>
          )}
        </View>

        <Pressable
          onPress={() => nudge(step)}
          accessibilityRole="button"
          accessibilityLabel="More"
          style={styles.stepButton}
        >
          <Text style={styles.stepGlyph}>+</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: space.md },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    backgroundColor: color.wash,
  },
  chipOn: { backgroundColor: color.accent },
  chipLabel: { ...text.label, fontSize: 13 },
  chipLabelOn: { color: color.onDark },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: radius.md,
    backgroundColor: color.wash,
    padding: space.xs,
  },
  stepButton: {
    width: HIT_SLOP_MIN,
    height: HIT_SLOP_MIN,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
    backgroundColor: color.surface,
  },
  stepGlyph: { ...text.title, fontSize: 22, lineHeight: 26 },
  readout: { alignItems: 'center', gap: 2 },
  amount: { ...text.numeric, fontSize: 20 },
  grams: { ...text.bodyMuted, fontSize: 12 },
});
