/**
 * Circular progress ring — the signature mark of the CalDiet look.
 *
 * One component at every size: the large calorie ring on the dashboard, the
 * small rings on each macro tile. SVG rather than a border trick because a
 * border can only draw quarters; a stroke with `strokeDasharray` draws any
 * fraction with round caps.
 */

import { StyleSheet, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';

import { color } from '@/theme/tokens';

interface ProgressRingProps {
  /** 0..1. Values beyond 1 render as a full ring — over target is still "full". */
  progress: number;
  size: number;
  strokeWidth: number;
  /** Ring colour. */
  tint: string;
  /** Track colour behind the progress stroke. */
  track?: string;
  /** Rendered in the centre of the ring. */
  children?: React.ReactNode;
}

export function ProgressRing({
  progress,
  size,
  strokeWidth,
  tint,
  track = color.wash,
  children,
}: ProgressRingProps) {
  const clamped = Math.max(0, Math.min(1, progress));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

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
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={tint}
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          // Dash offset shrinks as progress grows, revealing the stroke.
          strokeDashoffset={circumference * (1 - clamped)}
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
