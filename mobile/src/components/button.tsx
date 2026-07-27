/**
 * Buttons.
 *
 * Three variants, and the restraint is the point: `primary` is the indigo pill
 * that says "this is the thing to do here", `secondary` is a quiet tinted pill
 * for the alternative, and `ghost` is text-only for the escape hatch. A screen
 * showing two primaries is a screen that has not decided what it wants.
 *
 * Presses spring inward rather than fading. A fading button reads as disabling
 * itself under your thumb; one that presses in reads as accepting the touch.
 */

import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { PressableScale } from '@/components/motion';
import { HIT_SLOP_MIN, color, elevation, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

type Variant = 'primary' | 'secondary' | 'ghost';

interface ButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  /** Shows a spinner and blocks presses. Use while a submit is in flight. */
  loading?: boolean;
  variant?: Variant;
  /** Optional leading glyph, already rendered — usually an icon element. */
  icon?: React.ReactNode;
}

export function Button({
  label,
  onPress,
  disabled = false,
  loading = false,
  variant = 'primary',
  icon,
}: ButtonProps) {
  // Blocking presses while loading is what prevents a double-tap creating two
  // accounts, or firing two logins that each mint a session.
  const inert = disabled || loading;
  const onAccent = variant === 'primary';

  return (
    <PressableScale
      onPress={onPress}
      disabled={inert}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: inert, busy: loading }}
      style={[styles.base, styles[variant], inert && styles.disabled]}
    >
      {loading ? (
        <ActivityIndicator color={onAccent ? color.onDark : color.accent} />
      ) : (
        <View style={styles.content}>
          {icon}
          <Text style={[styles.label, onAccent ? styles.labelOnAccent : styles.labelOnLight]}>
            {label}
          </Text>
        </View>
      )}
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 54,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: space.xl,
    borderRadius: radius.pill,
    minWidth: HIT_SLOP_MIN,
  },
  content: { flexDirection: 'row', alignItems: 'center', gap: space.sm },

  // The indigo pill. Lifted, because the primary action should look like it
  // sits above the page rather than being painted onto it.
  primary: { backgroundColor: color.accent, ...elevation.mid },
  // Same shape, no weight, accent-tinted. Reads as available but secondary.
  secondary: { backgroundColor: color.accentTint },
  ghost: { backgroundColor: 'transparent', minHeight: HIT_SLOP_MIN },

  disabled: { opacity: 0.4 },

  label: { ...text.label, fontSize: 16 },
  labelOnAccent: { color: color.onDark },
  labelOnLight: { color: color.accent },
});
