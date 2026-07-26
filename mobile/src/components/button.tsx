/**
 * Primary button.
 *
 * `Pressable` rather than `TouchableOpacity`: it exposes a `pressed` state we can
 * style deliberately (a colour shift to `clayDeep`) instead of the blanket
 * opacity fade, which washes out the label as well as the background.
 */

import { Pressable, StyleSheet, Text } from 'react-native';

import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

interface ButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}

export function Button({ label, onPress, disabled = false }: ButtonProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      style={({ pressed }) => [
        styles.base,
        pressed && styles.pressed,
        disabled && styles.disabled,
      ]}
    >
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: HIT_SLOP_MIN,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: space.xl,
    backgroundColor: color.clay,
    borderRadius: radius.md,
  },
  pressed: {
    backgroundColor: color.clayDeep,
  },
  disabled: {
    opacity: 0.45,
  },
  label: {
    ...text.label,
    // White on `clay` clears AA for body text; the macro colours never carry
    // small text for exactly this reason.
    color: color.onDark,
  },
});
