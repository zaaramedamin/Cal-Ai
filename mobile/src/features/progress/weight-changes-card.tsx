/**
 * Weight change over 3, 7, 14, 30 and 90 days, and all time.
 *
 * Six rows rather than a chart, because the question this answers is not "what
 * shape was the last month" — the chart above already answers that — but "am I
 * moving, and how fast". That is six subtractions, and a number is a better
 * answer to it than a line.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { StyleSheet, Text, View } from 'react-native';

import { Card } from '@/components/card';
import {
  type WeightPoint,
  trendOf,
  weightChanges,
} from '@/features/progress/weight-changes';
import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

const TREND = {
  up: { icon: 'arrow-up' as const, tint: color.warning },
  down: { icon: 'arrow-down' as const, tint: color.positive },
  flat: { icon: 'arrow-forward' as const, tint: color.inkFaint },
  unknown: { icon: 'remove' as const, tint: color.inkFaint },
};

export function WeightChangesCard({ series }: { series: WeightPoint[] }) {
  const t = useT();
  const rows = weightChanges(series);

  return (
    <Card style={styles.card}>
      <Text style={text.heading}>{t('progress.weightChanges')}</Text>

      <View style={styles.rows}>
        {rows.map((row) => {
          const trend = trendOf(row.deltaKg);
          const { icon, tint } = TREND[trend];

          return (
            <View key={row.label} style={styles.row}>
              <Text style={styles.window}>{row.label}</Text>

              <View style={[styles.rule, { backgroundColor: tint }]} />

              <Text style={styles.delta}>
                {row.deltaKg === null
                  ? '—'
                  : `${row.deltaKg > 0 ? '+' : ''}${row.deltaKg.toFixed(1)} kg`}
              </Text>

              <Ionicons name={icon} size={16} color={tint} />

              <Text style={[styles.verdict, { color: tint }]} numberOfLines={2}>
                {/* "Not enough data" rather than "no change": one weigh-in is
                    not evidence of stability, and saying so would be a claim
                    nobody measured. */}
                {row.deltaKg === null
                  ? t('progress.notEnoughData')
                  : trend === 'flat'
                    ? t('progress.noChange')
                    : trend === 'up'
                      ? t('progress.gained')
                      : t('progress.lost')}
              </Text>
            </View>
          );
        })}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.lg, paddingVertical: space.xl },
  rows: { gap: space.lg },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  window: { ...text.bodyMuted, width: 62 },
  rule: { width: 20, height: 2, borderRadius: radius.pill },
  delta: { ...text.numeric, fontSize: 17, flex: 1, textAlign: 'right' },
  verdict: { ...text.bodyMuted, fontSize: 12, width: 74 },
});
