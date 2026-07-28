/**
 * The figure on the dashboard, drawn from the user's own height and weight.
 *
 * Built from SVG paths whose control points are recomputed inside a worklet, so
 * the silhouette **morphs** when the weight changes rather than cutting to a new
 * picture. That is the animation worth having here: watching the shape ease over
 * three weeks of logging is the feature; a shape that pops between two states
 * looks like a rendering bug.
 *
 * Deliberately abstract. No face, no clothing, no gender cues beyond the
 * proportions the numbers imply — this is a silhouette standing in for a body,
 * not a portrait of one. See `features/body/shape.ts` for why the visual range
 * is as narrow as it is.
 */

import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedProps,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, Defs, G, LinearGradient, Path, Stop } from 'react-native-svg';

import { bodyShape } from '@/features/body/shape';
import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

const AnimatedPath = Animated.createAnimatedComponent(Path);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

/** Drawing canvas. The figure is laid out in these units and scaled to fit. */
const VIEW_W = 120;
const VIEW_H = 210;
const CENTRE = VIEW_W / 2;

/** Slow on purpose — this is a shape settling, not a control responding. */
const MORPH_MS = 900;

interface BodyAvatarProps {
  heightCm: number;
  weightKg: number;
  size?: number;
}

export function BodyAvatar({ heightCm, weightKg, size = 190 }: BodyAvatarProps) {
  const target = bodyShape(weightKg, heightCm);

  // Starts at the current shape rather than at zero, so the figure does not
  // inflate from nothing every time the dashboard mounts.
  const width = useSharedValue(target.width);

  useEffect(() => {
    width.value = withTiming(target.width, {
      duration: MORPH_MS,
      easing: Easing.inOut(Easing.cubic),
    });
  }, [target.width, width]);

  // --- the silhouette, rebuilt as `width` animates ------------------------
  // Each of these is a worklet: it runs on the UI thread on every frame, so the
  // path is regenerated there rather than round-tripping through React.

  const torsoProps = useAnimatedProps(() => {
    'worklet';
    const w = width.value;
    const shoulder = 26 * w;
    const waist = 20 * w;
    const hip = 24 * w;

    // Shoulders -> waist -> hips, mirrored, with the waist pulled in less as the
    // figure widens. That single asymmetry is what stops a heavier silhouette
    // reading as "a thin person scaled up".
    return {
      d:
        `M ${CENTRE - shoulder} 62 ` +
        `C ${CENTRE - shoulder} 62 ${CENTRE - waist} 88 ${CENTRE - waist} 104 ` +
        `C ${CENTRE - waist} 118 ${CENTRE - hip} 124 ${CENTRE - hip} 134 ` +
        `L ${CENTRE + hip} 134 ` +
        `C ${CENTRE + hip} 124 ${CENTRE + waist} 118 ${CENTRE + waist} 104 ` +
        `C ${CENTRE + waist} 88 ${CENTRE + shoulder} 62 ${CENTRE + shoulder} 62 ` +
        `C ${CENTRE + shoulder} 56 ${CENTRE - shoulder} 56 ${CENTRE - shoulder} 62 Z`,
    };
  });

  const armsProps = useAnimatedProps(() => {
    'worklet';
    const w = width.value;
    const shoulder = 26 * w;
    const thickness = 6.5 * w;
    const out = 4 * w;

    const arm = (side: number) => {
      const top = CENTRE + side * (shoulder - 2);
      const bottom = CENTRE + side * (shoulder + out);
      return (
        `M ${top} 64 ` +
        `C ${bottom} 78 ${bottom} 96 ${bottom - side * 1.5} 118 ` +
        `L ${bottom - side * 1.5 + side * thickness} 118 ` +
        `C ${bottom + side * thickness} 96 ${bottom + side * thickness} 78 ` +
        `${top + side * thickness} 64 Z`
      );
    };

    return { d: `${arm(-1)} ${arm(1)}` };
  });

  const legsProps = useAnimatedProps(() => {
    'worklet';
    const w = width.value;
    const hip = 24 * w;
    const thigh = 10.5 * w;
    const gap = 2.5;

    const leg = (side: number) => {
      const outer = CENTRE + side * hip;
      const inner = CENTRE + side * gap;
      return (
        `M ${outer} 132 ` +
        `C ${outer} 156 ${outer - side * 1.5} 176 ${outer - side * 3} 198 ` +
        `L ${outer - side * (3 + thigh)} 198 ` +
        `C ${inner + side * 1} 176 ${inner} 156 ${inner} 132 Z`
      );
    };

    return { d: `${leg(-1)} ${leg(1)}` };
  });

  const headProps = useAnimatedProps(() => {
    'worklet';
    // The head barely changes — a head that grows with bodyweight is the single
    // fastest way to make a figure read as a caricature.
    return { r: 15 + (width.value - 1) * 2.5 };
  });

  // Height is not animated, because it does not move: a person's height is
  // fixed, so this scale is set once from the profile. Only the weight-driven
  // width is a shared value, which keeps one animated quantity on the UI thread
  // instead of two — and avoids animating an SVG transform string, which
  // react-native-svg handles far less reliably than a numeric prop.
  //
  // Scaled about the feet, so a taller figure grows upward rather than drifting
  // off the bottom of the frame.
  const s = target.scale;
  const transform = `translate(${CENTRE * (1 - s)}, ${VIEW_H * (1 - s)}) scale(${s})`;

  return (
    <Svg width={size * (VIEW_W / VIEW_H)} height={size} viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}>
      <Defs>
        <LinearGradient id="body" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={color.accent} stopOpacity="0.95" />
          <Stop offset="1" stopColor={color.accentDeep} stopOpacity="0.75" />
        </LinearGradient>
      </Defs>

      <G transform={transform}>
        <AnimatedCircle cx={CENTRE} cy={34} fill="url(#body)" animatedProps={headProps} />
        {/* Neck, drawn before the torso so the torso covers its lower edge. */}
        <Path
          d={`M ${CENTRE - 6} 46 L ${CENTRE + 6} 46 L ${CENTRE + 6} 64 L ${CENTRE - 6} 64 Z`}
          fill="url(#body)"
        />
        <AnimatedPath animatedProps={armsProps} fill="url(#body)" />
        <AnimatedPath animatedProps={torsoProps} fill="url(#body)" />
        <AnimatedPath animatedProps={legsProps} fill="url(#body)" />
      </G>
    </Svg>
  );
}

/**
 * The figure with its numbers beside it.
 *
 * BMI is shown because it is computed from data the user entered and is a real,
 * widely-used figure — but with the caveat, and without the category words. A
 * muscular person reads "overweight" on this scale, which is the measure's
 * well-known failure and not a fact about them.
 */
export function BodyCard({
  heightCm,
  weightKg,
  targetKg,
}: {
  heightCm: number;
  weightKg: number;
  targetKg: number | null;
}) {
  const t = useT();
  const shape = bodyShape(weightKg, heightCm);
  const remaining = targetKg === null ? null : Math.abs(weightKg - targetKg);

  return (
    <View style={styles.card}>
      <BodyAvatar heightCm={heightCm} weightKg={weightKg} size={168} />

      <View style={styles.readout}>
        <Text style={text.overline}>{t('body.title')}</Text>

        <View style={styles.statRow}>
          <Stat label={t('body.height')} value={`${Math.round(heightCm)} cm`} />
          <Stat label={t('body.weight')} value={`${weightKg.toFixed(1)} kg`} />
        </View>

        <View style={styles.bmiBlock}>
          <View style={styles.bmiHead}>
            <Text style={styles.bmiValue}>{shape.bmi.toFixed(1)}</Text>
            <Text style={styles.bmiLabel}>{t('body.bmi')}</Text>
          </View>
          <View style={styles.bmiTrack}>
            <View style={[styles.bmiDot, { left: `${shape.factor * 100}%` }]} />
          </View>
          <Text style={styles.caveat}>
{t('body.bmiCaveat')}
          </Text>
        </View>

        {remaining !== null && remaining >= 0.1 && (
          <Text style={styles.remaining}>
{t('body.toGoal', { remaining: remaining.toFixed(1), target: targetKg?.toFixed(0) ?? '' })}
          </Text>
        )}
        {remaining !== null && remaining < 0.1 && (
          <Text style={styles.reached}>{t('body.atGoal')}</Text>
        )}
      </View>
    </View>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.lg,
    padding: space.lg,
    borderRadius: radius.lg,
    backgroundColor: color.surface,
  },
  readout: { flex: 1, gap: space.sm },
  statRow: { flexDirection: 'row', gap: space.lg },
  stat: { gap: 1 },
  statValue: { ...text.numeric, fontSize: 18 },
  statLabel: { ...text.overline, fontSize: 9, color: color.inkMuted },

  bmiBlock: { gap: space.xs, marginTop: space.xs },
  bmiHead: { flexDirection: 'row', alignItems: 'baseline', gap: space.xs },
  bmiValue: { ...text.numeric, fontSize: 16 },
  bmiLabel: { ...text.overline, fontSize: 9, color: color.inkMuted },
  bmiTrack: {
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: color.wash,
    justifyContent: 'center',
  },
  bmiDot: {
    position: 'absolute',
    width: 8,
    height: 8,
    marginLeft: -4,
    borderRadius: radius.pill,
    backgroundColor: color.accent,
  },
  caveat: { ...text.bodyMuted, fontSize: 10, lineHeight: 13 },

  remaining: { ...text.bodyMuted, fontSize: 12 },
  reached: { ...text.bodyMuted, fontSize: 12, color: color.positive },
});
