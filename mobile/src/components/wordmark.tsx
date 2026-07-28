/**
 * The Cal Ai wordmark.
 *
 * Two words, not one, and the second carries the accent: "Cal" is what the app
 * counts, "Ai" is how it counts it. Splitting them and colouring the second is
 * what makes the name say what the product does at a glance — "CalAi" set in a
 * single weight reads as an unfamiliar noun the user has to decode.
 *
 * A component rather than a string repeated across screens, because a wordmark
 * that differs by a space or a shade on one screen stops being a wordmark.
 */

import { StyleSheet, Text, type TextStyle } from 'react-native';

import { color } from '@/theme/tokens';
import { fontFamily } from '@/theme/typography';

interface WordmarkProps {
  size?: number;
  /** Renders on a dark ground: "Cal" flips to white, "Ai" keeps the accent. */
  onDark?: boolean;
  style?: TextStyle;
}

export function Wordmark({ size = 24, onDark = false, style }: WordmarkProps) {
  return (
    <Text
      // Read aloud as the product name rather than as two fragments, which is
      // how a screen reader would otherwise announce the coloured span.
      accessibilityRole="header"
      accessibilityLabel="Cal Ai"
      style={[
        styles.base,
        { fontSize: size, letterSpacing: size * -0.025 },
        onDark && styles.onDark,
        style,
      ]}
    >
      Cal <Text style={styles.ai}>Ai</Text>
    </Text>
  );
}

const styles = StyleSheet.create({
  base: { fontFamily: fontFamily.extraBold, color: color.ink },
  onDark: { color: color.onDark },
  ai: { color: color.accent },
});
