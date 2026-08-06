/**
 * The macro bar — Cal Ai's signature element.
 *
 * A single horizontal meter split into protein, carbohydrate and fat as
 * proportions of the calories they contribute. It renders at three scales from
 * one component, and appears on every screen that shows food.
 *
 * **Why this rather than the ring the brief rules out.** A ring answers "what
 * percentage of my target have I eaten", which is one number the user could read
 * from the text anyway. This answers "what is my day actually made of", which is
 * the question a macro tracker exists for. It is linear, so it composes into
 * list rows and headers where a ring cannot, and it stays legible at 3px. Seeing
 * the same mark at every scale, on every screen, is what makes the app
 * recognisable at a glance.
 *
 * Proportions are by **calories contributed**, not grams. 100 g of fat and 100 g
 * of carbohydrate are not the same slice of a day: fat carries 9 kcal per gram
 * against 4. Splitting by grams would draw a picture that contradicts the
 * calorie total sitting next to it.
 */

import { StyleSheet, Text, View } from 'react-native';

import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

const KCAL_PER_GRAM = { protein: 4, carbs: 4, fat: 9 } as const;

const SCALE_HEIGHT = {
  hero: 12,
  row: 4,
  inline: 3,
} as const;

export type MacroBarScale = keyof typeof SCALE_HEIGHT;

export interface MacroGrams {
  protein_g: number;
  carbs_g: number;
  fat_g: number;
}

interface MacroBarProps {
  macros: MacroGrams;
  scale?: MacroBarScale;
  /** Shows "P 142g  C 198g  F 61g" beneath. Off at small scales by default. */
  showLegend?: boolean;
  /**
   * Draws a tick at the target's position. Only meaningful when the bar
   * represents consumption rather than a target itself.
   */
  targetCalories?: number;
}

export function MacroBar({
  macros,
  scale = 'row',
  showLegend = scale === 'hero',
  targetCalories,
}: MacroBarProps) {
  const t = useT();
  const kcal = {
    protein: macros.protein_g * KCAL_PER_GRAM.protein,
    carbs: macros.carbs_g * KCAL_PER_GRAM.carbs,
    fat: macros.fat_g * KCAL_PER_GRAM.fat,
  };
  const total = kcal.protein + kcal.carbs + kcal.fat;
  const height = SCALE_HEIGHT[scale];

  // An empty day is a real state, not an error: a fresh diary has no macros at
  // all. It renders as an empty track rather than a division by zero.
  const isEmpty = total <= 0;

  const tickPosition =
    targetCalories && total > 0 ? Math.min(1, targetCalories / total) : null;

  return (
    <View style={styles.wrapper}>
      <View
        style={[styles.track, { height, borderRadius: height / 2 }]}
        accessibilityRole="progressbar"
        accessibilityLabel={
          isEmpty
            ? t('macro.noneLogged')
            : t('macro.reading', {
                protein: macros.protein_g,
                carbs: macros.carbs_g,
                fat: macros.fat_g,
              })
        }
      >
        {!isEmpty && (
          <>
            <View style={{ flex: kcal.protein, backgroundColor: color.protein }} />
            <View style={{ flex: kcal.carbs, backgroundColor: color.carbs }} />
            <View style={{ flex: kcal.fat, backgroundColor: color.fat }} />
          </>
        )}
      </View>

      {tickPosition !== null && tickPosition < 1 && (
        <View
          style={[styles.tick, { left: `${tickPosition * 100}%`, height: height + 6 }]}
          pointerEvents="none"
        />
      )}

      {showLegend && (
        <View style={styles.legend}>
          <LegendItem
            swatch={color.protein}
            label={t('macro.proteinShort')}
            grams={macros.protein_g}
          />
          <LegendItem swatch={color.carbs} label={t('macro.carbsShort')} grams={macros.carbs_g} />
          <LegendItem swatch={color.fat} label={t('macro.fatShort')} grams={macros.fat_g} />
        </View>
      )}
    </View>
  );
}

function LegendItem({
  swatch,
  label,
  grams,
}: {
  swatch: string;
  label: string;
  grams: number;
}) {
  return (
    <View style={styles.legendItem}>
      {/* The swatch carries the colour; the letter carries the meaning. Colour
          is never the only signal — roughly 1 in 12 men cannot reliably separate
          some of these hues. */}
      <View style={[styles.swatch, { backgroundColor: swatch }]} />
      <Text style={styles.legendLabel}>{label}</Text>
      <Text style={styles.legendValue}>{Math.round(grams)}g</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    position: 'relative',
  },
  track: {
    flexDirection: 'row',
    overflow: 'hidden',
    backgroundColor: color.inkWash,
    width: '100%',
  },
  tick: {
    position: 'absolute',
    top: -3,
    width: 2,
    backgroundColor: color.ink,
    opacity: 0.55,
  },
  legend: {
    flexDirection: 'row',
    marginTop: space.sm,
    gap: space.lg,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  swatch: {
    width: 8,
    height: 8,
    borderRadius: radius.sm,
  },
  legendLabel: {
    ...text.overline,
    color: color.inkMuted,
  },
  legendValue: {
    ...text.numeric,
  },
});
