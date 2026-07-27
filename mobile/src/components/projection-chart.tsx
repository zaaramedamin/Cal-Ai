/**
 * The "with CalAi / without CalAi" weight projection.
 *
 * **This chart is illustrative, and the code says so out loud.**
 *
 * The curve is not a prediction derived from data — it is a shape drawn between
 * the user's current weight and the target their own inputs imply. Apps in this
 * category routinely present exactly this picture as though it were a forecast,
 * with an invented "without us" line that climbs for no reason. We draw the
 * comparison because the user asked for this design, but the component keeps the
 * dishonesty out of the numbers: both endpoints are real (today's weight, the
 * target and date the maths produced), only the path between them is decoration,
 * and the screen using this must label it.
 *
 * Built on react-native-svg, already a dependency for the progress rings.
 */

import Svg, { Defs, LinearGradient, Path, Stop, Circle } from 'react-native-svg';
import { StyleSheet, Text, View } from 'react-native';

import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

interface ProjectionChartProps {
  /** Weight today, in the unit being displayed. */
  startValue: number;
  /** Weight the plan targets. */
  endValue: number;
  /** Unit label shown in the endpoint pills, e.g. "kg" or "lbs". */
  unit: string;
  /** Date label under the right-hand endpoint. */
  endLabel: string;
  height?: number;
}

/**
 * An ease-in-out cubic, sampled.
 *
 * Chosen over a straight line because weight change genuinely is not linear —
 * there is a slow start and a plateau — so the S-curve is the honest shape even
 * though the exact path is illustrative. Sampled into a polyline-with-curves
 * rather than a single bezier so the same helper can draw either direction.
 */
function easeInOut(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

function curvePath(
  width: number,
  height: number,
  from: number,
  to: number,
  ease: (t: number) => number,
): string {
  const steps = 40;
  const points: string[] = [];
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const x = t * width;
    const y = from + (to - from) * ease(t);
    points.push(`${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`);
  }
  return points.join(' ');
}

export function ProjectionChart({
  startValue,
  endValue,
  unit,
  endLabel,
  height = 190,
}: ProjectionChartProps) {
  // Fixed viewBox with preserveAspectRatio off: the SVG scales to whatever width
  // the card gives it, so the chart never needs to measure its own layout.
  const W = 320;
  const H = height;
  const padTop = 28;
  const padBottom = 34;
  const usable = H - padTop - padBottom;

  const losing = endValue < startValue;
  // The "with CalAi" line always travels most of the vertical space, so the
  // shape reads the same whether the goal is loss or gain.
  const startY = losing ? padTop : padTop + usable;
  const endY = losing ? padTop + usable : padTop;

  const withPath = curvePath(W, H, startY, endY, easeInOut);
  // The comparison line drifts gently the *other* way, and only slightly — a
  // dramatic opposite curve would be a claim we cannot support.
  const withoutEndY = losing ? padTop + usable * 0.22 : padTop + usable * 0.78;
  const withoutPath = curvePath(W, H, startY, withoutEndY, (t) => t * t);

  return (
    <View style={styles.wrap}>
      <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <Defs>
          <LinearGradient id="withFill" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color.fat} stopOpacity="0.28" />
            <Stop offset="1" stopColor={color.fat} stopOpacity="0.02" />
          </LinearGradient>
          <LinearGradient id="withoutFill" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color.protein} stopOpacity="0.14" />
            <Stop offset="1" stopColor={color.protein} stopOpacity="0.02" />
          </LinearGradient>
        </Defs>

        <Path d={`${withoutPath} L${W},${H} L0,${H} Z`} fill="url(#withoutFill)" />
        <Path d={`${withPath} L${W},${H} L0,${H} Z`} fill="url(#withFill)" />

        <Path d={withoutPath} stroke={color.protein} strokeWidth={2.5} fill="none" />
        <Path d={withPath} stroke={color.fat} strokeWidth={3} fill="none" />

        <Circle cx={0} cy={startY} r={5} fill={color.surface} stroke={color.fat} strokeWidth={3} />
        <Circle cx={W} cy={endY} r={5} fill={color.surface} stroke={color.fat} strokeWidth={3} />
        <Circle
          cx={W}
          cy={withoutEndY}
          r={5}
          fill={color.surface}
          stroke={color.protein}
          strokeWidth={3}
        />
      </Svg>

      {/* Endpoint pills are absolutely positioned rather than drawn as SVG text,
          so they use the app's real type styles instead of a second font stack. */}
      <View style={[styles.pill, styles.pillStart]}>
        <Text style={styles.pillStartText}>
          {Math.round(startValue)} {unit}
        </Text>
      </View>
      <View style={[styles.pill, styles.pillEnd, losing ? styles.pillLow : styles.pillHigh]}>
        <Text style={styles.pillEndText}>
          {Math.round(endValue)} {unit}
        </Text>
      </View>

      <Text style={[styles.axis, styles.axisLeft]}>Now</Text>
      <Text style={[styles.axis, styles.axisRight]}>{endLabel}</Text>
      <Text style={styles.withoutLabel}>Without CalAi</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'relative' },
  pill: {
    position: 'absolute',
    paddingHorizontal: space.sm,
    paddingVertical: 3,
    borderRadius: radius.sm,
  },
  pillStart: { top: 0, left: 0, backgroundColor: 'rgba(76, 134, 232, 0.14)' },
  pillEnd: { backgroundColor: color.fat },
  pillLow: { bottom: 40, right: 0 },
  pillHigh: { top: 0, right: 0 },
  pillStartText: { ...text.numeric, fontSize: 13, color: color.fat },
  pillEndText: { ...text.numeric, fontSize: 13, color: color.onDark },
  axis: { ...text.bodyMuted, fontSize: 12, position: 'absolute', bottom: 0 },
  axisLeft: { left: 0 },
  axisRight: { right: 0 },
  withoutLabel: {
    ...text.label,
    fontSize: 12,
    color: color.protein,
    position: 'absolute',
    top: 34,
    right: 0,
  },
});
