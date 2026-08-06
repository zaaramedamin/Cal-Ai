/**
 * A back arrow, for every pushed screen that has nothing else to leave by.
 *
 * Android has a hardware back gesture and iOS has an edge swipe, so a screen
 * without a visible control is not strictly a dead end — but "not strictly a
 * dead end" is a bad standard for the only way out of a screen. Several screens
 * here (photo credits, my reports, my submissions, the custom-food form) had no
 * on-screen affordance at all.
 *
 * A chevron rather than a "Cancel" or "Done" word, because those promise
 * something about what happens to your input and this promises nothing: it goes
 * back. Screens that genuinely cancel or commit keep their own wording.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useT } from '@/i18n';
import { HIT_SLOP_MIN, color, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

interface BackHeaderProps {
  /** Small caps label beside the arrow. Usually where you are. */
  title?: string;
  /** Overrides `router.back()` — for a screen reached by `replace`. */
  onPress?: () => void;
}

export function BackHeader({ title, onPress }: BackHeaderProps) {
  const router = useRouter();
  const t = useT();

  return (
    <View style={styles.row}>
      <Pressable
        onPress={onPress ?? (() => router.back())}
        accessibilityRole="button"
        accessibilityLabel={t('a11y.goBack')}
        // The tap target is the whole 44pt square, not the 22pt glyph. A back
        // arrow that needs aiming at is the one control that must never miss.
        hitSlop={8}
        style={styles.button}
      >
        <Ionicons name="chevron-back" size={24} color={color.ink} />
      </Pressable>
      {title ? <Text style={text.overline}>{title}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.xs, marginBottom: space.sm },
  button: {
    width: HIT_SLOP_MIN,
    height: HIT_SLOP_MIN,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: -space.md,
  },
});
