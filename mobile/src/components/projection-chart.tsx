/**
 * The "with Cal Ai / without Cal Ai" weight projection.
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

import { useT } from '@/i18n';
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

/**
 * Horizontal room kept clear at each end of the curves.
 *
 * The endpoint dots are drawn *on* the first and last points, and with the
 * curves running from x=0 to x=W exactly, half of every dot fell outside the
 * viewBox and was clipped into a semicircle. The inset is the dot's radius plus
 * its stroke.
 */
const INSET_X = 8;

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
    const x = INSET_X + t * (width - INSET_X * 2);
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
  const t = useT();

  // Fixed viewBox with preserveAspectRatio off: the SVG scales to whatever width
  // the card gives it, so the chart never needs to measure its own layout.
  const W = 320;
  const H = height;
  const padTop = 28;
  const padBottom = 34;
  const usable = H - padTop - padBottom;

  const losing = endValue < startValue;
  // The "with Cal Ai" line always travels most of the vertical space, so the
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
          {/* The plan in the action colour, the counterfactual in neutral grey.
              These were fat-blue and protein-red, which on a nutrition app read
              as two macros rather than "with" and "without". */}
          <LinearGradient id="withFill" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color.accent} stopOpacity="0.24" />
            <Stop offset="1" stopColor={color.accent} stopOpacity="0.02" />
          </LinearGradient>
          <LinearGradient id="withoutFill" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color.ink} stopOpacity="0.06" />
            <Stop offset="1" stopColor={color.ink} stopOpacity="0.01" />
          </LinearGradient>
        </Defs>

        <Path d={`${withoutPath} L${W - INSET_X},${H} L${INSET_X},${H} Z`} fill="url(#withoutFill)" />
        <Path d={`${withPath} L${W - INSET_X},${H} L${INSET_X},${H} Z`} fill="url(#withFill)" />

        <Path
          d={withoutPath}
          stroke={color.inkFaint}
          strokeWidth={2.5}
          strokeDasharray="6 5"
          fill="none"
        />
        <Path d={withPath} stroke={color.accent} strokeWidth={3} fill="none" />

        <Circle cx={INSET_X} cy={startY} r={5} fill={color.surface} stroke={color.accent} strokeWidth={3} />
        <Circle cx={W - INSET_X} cy={endY} r={5} fill={color.surface} stroke={color.accent} strokeWidth={3} />
        <Circle
          cx={W - INSET_X}
          cy={withoutEndY}
          r={5}
          fill={color.surface}
          stroke={color.inkFaint}
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

      <Text style={[styles.axis, styles.axisLeft]}>{t('chart.now')}</Text>
      <Text style={[styles.axis, styles.axisRight]}>{endLabel}</Text>
      {/* Placed from where the grey line actually ends. It was pinned near the
          top, which is right for losing weight and put it beside the *wrong*
          line for gaining, where the grey curve finishes low. The SVG's height
          is H pixels with no vertical scaling, so the y maps directly. */}
      <Text style={[styles.withoutLabel, { top: withoutEndY - 26 }]}>{t('chart.without')}</Text>
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
  pillStart: { top: 0, left: 0, backgroundColor: color.accentTint },
  pillEnd: { backgroundColor: color.accent },
  pillLow: { bottom: 40, right: 0 },
  pillHigh: { top: 0, right: 0 },
  pillStartText: { ...text.numeric, fontSize: 13, color: color.accent },
  pillEndText: { ...text.numeric, fontSize: 13, color: color.onDark },
  axis: { ...text.bodyMuted, fontSize: 12, position: 'absolute', bottom: 0 },
  axisLeft: { left: 0 },
  axisRight: { right: 0 },
  withoutLabel: {
    ...text.label,
    fontSize: 12,
    color: color.inkMuted,
    position: 'absolute',
    right: 0,
  },
});
