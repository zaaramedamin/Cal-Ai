/**
 * Primary button.
 *
 * `Pressable` rather than `TouchableOpacity`: it exposes a `pressed` state we can
 * style deliberately (a colour shift to `clayDeep`) instead of the blanket
 * opacity fade, which washes out the label as well as the background.
 */

import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

interface ButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  /** Shows a spinner and blocks presses. Use while a submit is in flight. */
  loading?: boolean;
}

export function Button({ label, onPress, disabled = false, loading = false }: ButtonProps) {
  // Blocking presses while loading is what prevents a double-tap creating two
  // accounts, or firing two logins that each mint a session.
  const inert = disabled || loading;

  return (
    <Pressable
      onPress={onPress}
      disabled={inert}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: inert, busy: loading }}
      style={({ pressed }) => [styles.base, pressed && styles.pressed, inert && styles.disabled]}
    >
      {loading ? (
        <ActivityIndicator color={color.onDark} />
      ) : (
        <Text style={styles.label}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 52,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: space.xl,
    // Black pill — the single action treatment of the whole app. One button
    // style everywhere is what makes the primary action instantly findable.
    backgroundColor: color.ink,
    borderRadius: radius.pill,
    minWidth: HIT_SLOP_MIN,
  },
  pressed: {
    opacity: 0.85,
  },
  disabled: {
    opacity: 0.35,
  },
  label: {
    ...text.label,
    fontSize: 16,
    color: color.onDark,
  },
});
