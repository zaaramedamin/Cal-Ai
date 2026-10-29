/**
 * Shared chrome for the onboarding funnel.
 *
 * A progress bar with a back button, the option cards, and the small
 * achievement curve — pulled out here because the funnel is a dozen screens
 * that must look identical. Duplicating this per step is how a funnel ends up
 * with three slightly different bar heights.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import type { ReactNode } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import Svg, { Defs, LinearGradient, Path, Stop, Circle } from 'react-native-svg';

import { useT } from '@/i18n';
import { type PhotoSlot, photo } from '@/theme/imagery';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { fontFamily, text } from '@/theme/typography';

/* -------------------------------------------------------------------------- */

export function FunnelHeader({
  progress,
  onBack,
}: {
  /** 0–1. Drives the bar width. */
  progress: number;
  onBack: () => void;
}) {
  const t = useT();

  return (
    <View style={styles.header}>
      <Pressable
        onPress={onBack}
        accessibilityRole="button"
        accessibilityLabel={t('a11y.goBack')}
        style={styles.backButton}
      >
        <Ionicons name="arrow-back" size={22} color={color.ink} />
      </Pressable>
      <View
        style={styles.track}
        accessibilityRole="progressbar"
        accessibilityValue={{ now: Math.round(progress * 100), min: 0, max: 100 }}
      >
        <View style={[styles.fill, { width: `${Math.min(100, Math.max(0, progress * 100))}%` }]} />
      </View>
    </View>
  );
}

/* -------------------------------------------------------------------------- */

export function FunnelStep({
  title,
  subtitle,
  children,
  footnote,
  image,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** Small print pinned above the action, e.g. the data-deletion promise. */
  footnote?: string;
  /** A photograph above the heading. Omitted steps look exactly as before. */
  image?: PhotoSlot;
}) {
  const picture = image ? photo(image) : null;

  return (
    <View style={styles.step}>
      {picture && <Image source={picture} style={styles.stepPhoto} resizeMode="cover" />}
      <Text style={styles.stepTitle}>{title}</Text>
      {subtitle && <Text style={styles.stepSubtitle}>{subtitle}</Text>}
      {/* The body is centred in the space between heading and button, which is
          what gives every step in the funnel the same rhythm regardless of
          whether it holds four cards or one ruler. */}
      <View style={styles.stepBody}>{children}</View>
      {footnote && <Text style={styles.footnote}>{footnote}</Text>}
    </View>
  );
}

/* -------------------------------------------------------------------------- */

export function ChoiceCard({
  label,
  description,
  icon,
  selected,
  onPress,
}: {
  label: string;
  description?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      style={({ pressed }) => [
        styles.choice,
        selected && styles.choiceSelected,
        pressed && styles.choicePressed,
      ]}
    >
      {icon && (
        <Ionicons
          name={icon}
          size={22}
          color={selected ? color.onDark : color.ink}
          style={styles.choiceIcon}
        />
      )}
      <View style={styles.choiceText}>
        <Text style={[styles.choiceLabel, selected && styles.onDark]}>{label}</Text>
        {description && (
          <Text style={[styles.choiceDescription, selected && styles.onDarkMuted]}>
            {description}
          </Text>
        )}
      </View>
    </Pressable>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * The small rising curve used on the encouragement steps.
 *
 * Purely illustrative and labelled as such by the screens that use it — it
 * plots no data. It exists to make the funnel feel like progress rather than
 * a form, which is the whole point of those screens.
 */
export function AchievementCurve({ height = 160 }: { height?: number }) {
  const W = 300;
  const H = height;
  const pad = 16;

  const path = `M${pad},${H - pad - 10}
    C${W * 0.3},${H - pad - 14} ${W * 0.42},${H - pad - 40} ${W * 0.55},${H * 0.45}
    S${W * 0.8},${pad + 6} ${W - pad},${pad + 4}`;

  return (
    <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}>
      <Defs>
        <LinearGradient id="achieve" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={color.positive} stopOpacity="0.30" />
          <Stop offset="1" stopColor={color.positive} stopOpacity="0.02" />
        </LinearGradient>
      </Defs>
      <Path d={`${path} L${W - pad},${H - pad} L${pad},${H - pad} Z`} fill="url(#achieve)" />
      <Path d={path} stroke={color.positive} strokeWidth={3} fill="none" strokeLinecap="round" />
      {[
        [pad, H - pad - 10],
        [W * 0.55, H * 0.45],
        [W - pad, pad + 4],
      ].map(([cx, cy], index) => (
        <Circle
          key={index}
          cx={cx}
          cy={cy}
          r={5}
          fill={color.surface}
          stroke={color.positive}
          strokeWidth={3}
        />
      ))}
    </Svg>
  );
}

/* -------------------------------------------------------------------------- */

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: space.lg, marginBottom: space.xl },
  backButton: {
    width: HIT_SLOP_MIN,
    height: HIT_SLOP_MIN,
    borderRadius: radius.pill,
    backgroundColor: color.wash,
    alignItems: 'center',
    justifyContent: 'center',
  },
  track: { flex: 1, height: 6, borderRadius: radius.pill, backgroundColor: color.wash },
  fill: { height: 6, borderRadius: radius.pill, backgroundColor: color.accent },

  step: { flex: 1 },
  stepPhoto: { width: '100%', height: 150, borderRadius: radius.lg, marginBottom: space.lg },
  stepTitle: {
    fontFamily: fontFamily.extraBold,
    fontSize: 30,
    lineHeight: 36,
    letterSpacing: -0.8,
    color: color.ink,
  },
  stepSubtitle: { ...text.bodyMuted, fontSize: 15, marginTop: space.sm },
  stepBody: { flex: 1, justifyContent: 'center', gap: space.md, paddingVertical: space.xl },
  footnote: { ...text.bodyMuted, fontSize: 12, marginBottom: space.md },

  choice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 62,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.md,
    backgroundColor: color.wash,
  },
  choiceSelected: { backgroundColor: color.accent },
  choicePressed: { opacity: 0.75 },
  choiceIcon: { width: 26, textAlign: 'center' },
  choiceText: { flex: 1, gap: 2 },
  choiceLabel: { ...text.label, fontSize: 16 },
  choiceDescription: { ...text.bodyMuted, fontSize: 13 },
  onDark: { color: color.onDark },
  onDarkMuted: { color: color.onDarkMuted },
});
