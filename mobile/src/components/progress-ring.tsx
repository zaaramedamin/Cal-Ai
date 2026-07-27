/**
 * Circular progress ring — the signature mark of the app.
 *
 * One component at every size: the large calorie ring on the dashboard, the
 * small rings on each macro tile. SVG rather than a border trick because a
 * border can only draw quarters; a stroke with `strokeDasharray` draws any
 * fraction with round caps.
 *
 * **Why it animates.** A ring that snaps to its value looks like a static
 * picture of a number you already knew. A ring that sweeps from empty tells you
 * two things the still image cannot — that the app just recalculated, and
 * roughly how far round the dial the value sits, because you watched it travel
 * there. The sweep runs once per value change, not on every render, so
 * scrolling past a macro tile does not restart it.
 */

import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedProps,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle } from 'react-native-svg';

import { color, duration } from '@/theme/tokens';

// Reanimated can only drive props on components it has wrapped. `Circle` is an
// SVG primitive, so it needs wrapping once here rather than inline, which would
// create a new component type on every render and remount the ring each time.
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

interface ProgressRingProps {
  /** 0..1. Values beyond 1 render as a full ring — over target is still "full". */
  progress: number;
  size: number;
  strokeWidth: number;
  /** Ring colour. */
  tint: string;
  /** Track colour behind the progress stroke. */
  track?: string;
  /** Skip the sweep, for rings that appear during a scroll rather than on load. */
  animate?: boolean;
  /** Rendered in the centre of the ring. */
  children?: React.ReactNode;
}

export function ProgressRing({
  progress,
  size,
  strokeWidth,
  tint,
  track = color.wash,
  animate = true,
  children,
}: ProgressRingProps) {
  const clamped = Math.max(0, Math.min(1, progress));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const swept = useSharedValue(animate ? 0 : clamped);

  useEffect(() => {
    swept.value = animate
      ? withTiming(clamped, {
          duration: duration.gentle,
          // Decelerating: quick off the mark, easing into the final value. A
          // linear sweep reads mechanical, and a bouncing one would overshoot
          // past a number the user is trying to read.
          easing: Easing.out(Easing.cubic),
        })
      : clamped;
  }, [clamped, animate, swept]);

  const animatedProps = useAnimatedProps(() => ({
    strokeDashoffset: circumference * (1 - swept.value),
  }));

  return (
    <View style={{ width: size, height: size }}>
      {/* Rotated -90° so progress starts at 12 o'clock, matching every ring the
          user has seen elsewhere; SVG circles natively start at 3 o'clock. */}
      <Svg width={size} height={size} style={styles.rotated}>
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={track}
          strokeWidth={strokeWidth}
          fill="none"
        />
        <AnimatedCircle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={tint}
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          animatedProps={animatedProps}
        />
      </Svg>
      <View style={styles.center}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  rotated: { transform: [{ rotate: '-90deg' }] },
  center: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
