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

const BANDS = [
  { key: 'underweight', tint: '#4C9AFF' },
  { key: 'healthy', tint: '#2ECC71' },
  { key: 'overweight', tint: '#F5B041' },
  { key: 'obese', tint: '#E74C3C' },
] as const;

type Category = (typeof BANDS)[number]['key'];

export function BmiCard({ bmi, category }: { bmi: number; category: Category | string }) {
  const t = useT();
  const band = BANDS.find((entry) => entry.key === category) ?? BANDS[1];

  const position = Math.min(1, Math.max(0, (bmi - MIN_BMI) / (MAX_BMI - MIN_BMI)));

  return (
    <Card style={styles.card}>
      <Text style={text.heading}>{t('progress.yourBmi')}</Text>

      <View style={styles.readout}>
        <Text style={styles.value}>{bmi.toFixed(1)}</Text>
        <Text style={styles.lead}>{t('progress.yourWeightIs')}</Text>
        <View style={[styles.pill, { backgroundColor: band.tint }]}>
          <Text style={styles.pillText}>{t(`progress.bmi.${band.key}` as never)}</Text>
        </View>
      </View>

      <View>
        <Svg width="100%" height={10}>
          <Defs>
            <LinearGradient id="bmiScale" x1="0" y1="0" x2="1" y2="0">
              <Stop offset="0" stopColor={BANDS[0].tint} />
              <Stop offset="0.33" stopColor={BANDS[1].tint} />
              <Stop offset="0.66" stopColor={BANDS[2].tint} />
              <Stop offset="1" stopColor={BANDS[3].tint} />
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
  pillText: { ...text.label, fontSize: 12, color: color.onDark },

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
