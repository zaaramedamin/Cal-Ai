/**
 * A vertical list of mutually exclusive choices.
 *
 * Used instead of a picker wheel or a dropdown throughout onboarding. Both of
 * those hide the alternatives until tapped, which is wrong when the choice
 * itself needs explaining — "moderate" means nothing without "exercise 3–5 days
 * a week" beside it. Showing every option with its description costs vertical
 * space and saves the user from guessing.
 */

import { Pressable, StyleSheet, Text, View } from 'react-native';

import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export interface Option<T extends string> {
  value: T;
  label: string;
  description?: string;
}

interface OptionListProps<T extends string> {
  options: readonly Option<T>[];
  value: T | null;
  onChange: (value: T) => void;
}

export function OptionList<T extends string>({ options, value, onChange }: OptionListProps<T>) {
  return (
    <View style={styles.list}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            onPress={() => onChange(option.value)}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            accessibilityLabel={option.label}
            accessibilityHint={option.description}
            style={({ pressed }) => [
              styles.option,
              selected && styles.optionSelected,
              pressed && styles.optionPressed,
            ]}
          >
            <View style={styles.optionText}>
              <Text style={[text.label, selected && styles.labelSelected]}>{option.label}</Text>
              {option.description && (
                <Text style={styles.description}>{option.description}</Text>
              )}
            </View>
            {/* A filled dot rather than only a border colour: selection must be
                readable without relying on the colour difference alone. */}
            <View style={[styles.radio, selected && styles.radioSelected]}>
              {selected && <View style={styles.radioDot} />}
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: space.sm,
  },
  option: {
    minHeight: HIT_SLOP_MIN,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    paddingVertical: space.md,
    paddingHorizontal: space.lg,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
    borderRadius: radius.md,
  },
  optionSelected: {
    borderColor: color.clay,
    backgroundColor: color.inkWash,
  },
  optionPressed: {
    opacity: 0.7,
  },
  optionText: {
    flex: 1,
    gap: 2,
  },
  labelSelected: {
    color: color.ink,
  },
  description: {
    ...text.bodyMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  radio: {
    width: 20,
    height: 20,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: color.inkFaint,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: {
    borderColor: color.clay,
  },
  radioDot: {
    width: 10,
    height: 10,
    borderRadius: radius.pill,
    backgroundColor: color.clay,
  },
});
