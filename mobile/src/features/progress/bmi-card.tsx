/**
 * BMI, with the band it falls in.
 *
 * **The caveat is not small print.** BMI cannot tell muscle from fat, and a
 * lifter reading "overweight" from an app that has just weighed their progress
 * is being told something false by a number that looks authoritative. The
 * category is shown because people expect it and it is the point of the measure,
 * but the sentence underneath is part of the card, not a footnote — the same
 * reason the projection screen says its curve is illustrative.
 *
 * The gradient is a real scale, not decoration: the marker sits at the position
 * the value actually occupies between 15 and 40, so two users can compare their
 * markers and the comparison means something.
 */

import { StyleSheet, Text, View } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

import { Card } from '@/components/card';
import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

/** The plotted range. Below and above this the marker simply pins to an end. */
const MIN_BMI = 15;
const MAX_BMI = 40;
/** Obese has no upper bound; the bar simply ends here. */
const MAX_BMI_BAND = MAX_BMI;

/**
 * The four WHO bands, in the app's own palette rather than a second set of
 * flat-UI hexes. `upTo` is each band's upper bound, which is what places the
 * colour stops: they used to sit at 0/33/66/100% of the bar, but on a 15–40
 * scale the real boundaries fall at 14%, 40% and 60% — so a BMI of 26,
 * "overweight", was drawn on green.
 */
const BANDS = [
  { key: 'underweight', upTo: 18.5, tint: color.fat, tintSoft: color.fatTint, ink: color.fatText },
  { key: 'healthy', upTo: 25, tint: color.positive, tintSoft: color.positiveTint, ink: color.positiveText },
  { key: 'overweight', upTo: 30, tint: color.warning, tintSoft: color.warningTint, ink: color.warningText },
  { key: 'obese', upTo: MAX_BMI_BAND, tint: color.danger, tintSoft: color.dangerTint, ink: color.dangerText },
] as const;

/** Where a BMI value falls along the bar, 0–1. */
function along(bmi: number): number {
  return Math.min(1, Math.max(0, (bmi - MIN_BMI) / (MAX_BMI - MIN_BMI)));
}

type Category = (typeof BANDS)[number]['key'];

export function BmiCard({ bmi, category }: { bmi: number; category: Category | string }) {
  const t = useT();
  const band = BANDS.find((entry) => entry.key === category) ?? BANDS[1];

  const position = along(bmi);

  // Each band gets a solid run with a short blend either side of its boundary,
  // so the colour under the marker is the colour of the category it names.
  const BLEND = 0.02;
  const stops = BANDS.flatMap((entry, index) => {
    const start = index === 0 ? 0 : along(BANDS[index - 1].upTo) + BLEND;
    const end = index === BANDS.length - 1 ? 1 : along(entry.upTo) - BLEND;
    return [
      { offset: start, color: entry.tint },
      { offset: end, color: entry.tint },
    ];
  });

  return (
    <Card style={styles.card}>
      <Text style={text.heading}>{t('progress.yourBmi')}</Text>

      <View style={styles.readout}>
        <Text style={styles.value}>{bmi.toFixed(1)}</Text>
        <Text style={styles.lead}>{t('progress.yourWeightIs')}</Text>
        {/* Tinted pill with deep text. White on the bright band colours was
            about 2:1 — the one word on this card that carries the verdict. */}
        <View style={[styles.pill, { backgroundColor: band.tintSoft }]}>
          <Text style={[styles.pillText, { color: band.ink }]}>
            {t(`progress.bmi.${band.key}` as never)}
          </Text>
        </View>
      </View>

      <View>
        <Svg width="100%" height={10}>
          <Defs>
            <LinearGradient id="bmiScale" x1="0" y1="0" x2="1" y2="0">
              {stops.map((stop, index) => (
                <Stop key={index} offset={stop.offset} stopColor={stop.color} />
              ))}
            </LinearGradient>
          </Defs>
          <Rect x="0" y="0" width="100%" height="10" rx="5" fill="url(#bmiScale)" />
        </Svg>

        {/* Positioned as a percentage so it stays correct on any screen width
            without measuring the bar first. */}
        <View style={[styles.marker, { left: `${position * 100}%` }]} />
      </View>

      <View style={styles.legend}>
        {BANDS.map((entry) => (
          <View key={entry.key} style={styles.legendItem}>
            <View style={[styles.dot, { backgroundColor: entry.tint }]} />
            <Text style={styles.legendText}>{t(`progress.bmi.${entry.key}` as never)}</Text>
          </View>
        ))}
      </View>

      <Text style={styles.caveat}>{t('body.bmiCaveat')}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.lg, paddingVertical: space.xl },
  readout: { flexDirection: 'row', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  value: { ...text.numeric, fontSize: 34, lineHeight: 40 },
  lead: { ...text.bodyMuted },
  pill: { paddingHorizontal: space.md, paddingVertical: space.xs, borderRadius: radius.pill },
  pillText: { ...text.label, fontSize: 12 },

  marker: {
    position: 'absolute',
    top: -3,
    width: 3,
    height: 16,
    borderRadius: 2,
    backgroundColor: color.ink,
    // Centres the marker on its value rather than starting at it, which would
    // read consistently low by half its width.
    marginLeft: -1.5,
  },

  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: space.md },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  dot: { width: 7, height: 7, borderRadius: 4 },
  legendText: { ...text.bodyMuted, fontSize: 11 },

  caveat: { ...text.bodyMuted, fontSize: 11, lineHeight: 16 },
});
