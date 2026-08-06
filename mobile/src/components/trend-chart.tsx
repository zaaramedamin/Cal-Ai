/**
 * A weight trend with its goal line.
 *
 * Shares the visual language of the onboarding projection — gradient area,
 * rounded curve, endpoint pills — but with one decisive difference: **every
 * point here is real.** The projection draws a shape between two known
 * endpoints; this plots readings the user actually logged. They are allowed to
 * look alike because they are about the same thing, and the goal line is what
 * ties the two together across the app.
 *
 * Drawn directly with react-native-svg. A charting library would be megabytes
 * of API surface for one polyline and a dashed rule.
 */

import Svg, { Circle, Defs, Line, LinearGradient, Path, Stop } from 'react-native-svg';
import { StyleSheet, Text, View } from 'react-native';

import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

interface TrendChartProps {
  values: number[];
  /** Draws a dashed goal line, when there is one. */
  target?: number | null;
  unit?: string;
  height?: number;
  /** Shown instead of the chart when there is not enough to plot. */
  emptyMessage?: string;
}

/**
 * A path through the points with gentle horizontal smoothing.
 *
 * Catmull-Rom-ish control points rather than straight segments, because daily
 * weight is noisy and a jagged line invites reading meaning into each spike.
 * The smoothing is horizontal only, so no drawn point ever sits at a value the
 * user did not log — a vertical smooth would invent readings.
 */
function smoothPath(points: { x: number; y: number }[]): string {
  if (points.length < 2) return '';
  let d = `M${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`;
  for (let i = 1; i < points.length; i += 1) {
    const previous = points[i - 1];
    const current = points[i];
    const midX = (previous.x + current.x) / 2;
    d += ` C${midX.toFixed(2)},${previous.y.toFixed(2)} ${midX.toFixed(2)},${current.y.toFixed(
      2,
    )} ${current.x.toFixed(2)},${current.y.toFixed(2)}`;
  }
  return d;
}

export function TrendChart({
  values,
  target = null,
  unit = 'kg',
  height = 130,
  emptyMessage,
}: TrendChartProps) {
  const t = useT();

  if (values.length < 2) {
    return <Text style={styles.empty}>{emptyMessage ?? t('trend.empty')}</Text>;
  }

  const W = 300;
  const H = height;
  const padY = 22;

  // The goal line is included in the vertical range so it is always on screen —
  // a target off the top of the chart tells the user nothing about the distance
  // still to cover, which is the one thing the line exists to show.
  const candidates = target === null ? values : [...values, target];
  const min = Math.min(...candidates);
  const max = Math.max(...candidates);
  const span = max - min || 1;

  const toY = (value: number) => padY + (H - padY * 2) * (1 - (value - min) / span);
  const step = W / (values.length - 1);
  const points = values.map((value, index) => ({ x: index * step, y: toY(value) }));

  const line = smoothPath(points);
  const area = `${line} L${W},${H} L0,${H} Z`;
  const last = values[values.length - 1];
  const first = values[0];
  const falling = last <= first;

  return (
    <View>
      <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <Defs>
          <LinearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color.ink} stopOpacity="0.16" />
            <Stop offset="1" stopColor={color.ink} stopOpacity="0" />
          </LinearGradient>
        </Defs>

        <Path d={area} fill="url(#trendFill)" />

        {target !== null && (
          <Line
            x1={0}
            y1={toY(target)}
            x2={W}
            y2={toY(target)}
            stroke={color.positive}
            strokeWidth={2}
            strokeDasharray="6 5"
          />
        )}

        <Path d={line} stroke={color.ink} strokeWidth={3} fill="none" strokeLinecap="round" />
        <Circle
          cx={points[points.length - 1].x}
          cy={points[points.length - 1].y}
          r={5}
          fill={color.surface}
          stroke={color.ink}
          strokeWidth={3}
        />
      </Svg>

      <View style={styles.legend}>
        <Text style={styles.legendItem}>
          {first.toFixed(1)} {unit} at the start
        </Text>
        {target !== null && (
          <View style={styles.goalTag}>
            <View style={styles.goalDash} />
            <Text style={styles.goalText}>
              goal {target.toFixed(1)} {unit}
            </Text>
          </View>
        )}
      </View>

      <Text style={styles.delta}>
        {first === last
          ? t('trend.noChange')
          : t('trend.soFar', {
              arrow: falling ? '↓' : '↑',
              amount: Math.abs(last - first).toFixed(1),
              unit,
            })}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  empty: { ...text.bodyMuted, fontSize: 13, paddingVertical: space.lg },
  legend: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: space.sm,
  },
  legendItem: { ...text.bodyMuted, fontSize: 11 },
  goalTag: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  goalDash: { width: 14, height: 2, borderRadius: radius.pill, backgroundColor: color.positive },
  goalText: { ...text.bodyMuted, fontSize: 11 },
  delta: { ...text.label, fontSize: 13, marginTop: space.xs },
});
