/**
 * Labelled text input with an error slot.
 *
 * The error lives inside the field rather than in a banner at the top of the
 * form, because a message next to the thing that is wrong needs no explanation
 * of which thing is wrong. The layout reserves no space for it — fields would
 * otherwise sit oddly far apart in the normal case where nothing is wrong.
 */

import { forwardRef, useState } from 'react';
import { StyleSheet, Text, TextInput, type TextInputProps, View } from 'react-native';

import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

interface TextFieldProps extends TextInputProps {
  label: string;
  error?: string | null;
  hint?: string;
}

export const TextField = forwardRef<TextInput, TextFieldProps>(function TextField(
  { label, error, hint, style, ...inputProps },
  ref,
) {
  const invalid = Boolean(error);
  // Focus is tracked in state rather than left to the platform default,
  // because the native highlight differs per OS and neither one matches the
  // accent. A field you are typing in should look unmistakably active.
  const [focused, setFocused] = useState(false);

  return (
    <View style={styles.wrapper}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        ref={ref}
        style={[
          styles.input,
          focused && styles.inputFocused,
          invalid && styles.inputInvalid,
          style,
        ]}
        placeholderTextColor={color.inkFaint}
        accessibilityLabel={label}
        // The error goes in the hint, so a screen reader announces it on focus
        // instead of relying on the red border, which conveys nothing to
        // someone who cannot see it. It used to pass only `hint`, and the
        // comment claimed the error was announced when it was not.
        accessibilityHint={error ?? hint}
        aria-invalid={invalid}
        {...inputProps}
        onFocus={(event) => {
          setFocused(true);
          inputProps.onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          inputProps.onBlur?.(event);
        }}
      />
      {invalid ? (
        <Text style={styles.error} accessibilityRole="alert">
          {error}
        </Text>
      ) : hint ? (
        <Text style={styles.hint}>{hint}</Text>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  wrapper: {
    gap: space.xs,
  },
  label: {
    ...text.overline,
    color: color.inkMuted,
  },
  // Only the colour changes on focus. The width used to go from 1 to 1.5 as
  // well, which pushed the text half a point sideways and grew the field by a
  // point on every tap — a small jolt, felt every time a form is used.
  inputFocused: {
    borderColor: color.accent,
  },
  input: {
    ...text.body,
    minHeight: HIT_SLOP_MIN,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    backgroundColor: color.surface,
    borderWidth: 1.5,
    borderColor: color.hairline,
    borderRadius: radius.md,
  },
  inputInvalid: {
    borderColor: color.danger,
  },
  error: {
    ...text.label,
    fontSize: 13,
    color: color.dangerText,
  },
  hint: {
    ...text.bodyMuted,
    fontSize: 13,
  },
});
