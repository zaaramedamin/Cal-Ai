/**
 * The white card — the basic surface of the whole UI.
 *
 * Everything content-bearing sits on one of these: the calorie ring, macro
 * tiles, list rows, charts. Centralising it means the radius and shadow are
 * decided once, and a future tweak to either restyles the entire app.
 */

import type { ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { cardShadow, color, radius, space } from '@/theme/tokens';

interface CardProps {
  children: ReactNode;
  /**
   * `StyleProp` rather than a bare `ViewStyle`, so callers can write the normal
   * `[base, condition && variant]` form. The narrower type rejected `false`,
   * which forced conditional styling into a ternary at every call site.
   */
  style?: StyleProp<ViewStyle>;
  /** Tighter padding for tiles that are mostly a single number. */
  compact?: boolean;
}

export function Card({ children, style, compact = false }: CardProps) {
  return (
    <View style={[styles.card, compact ? styles.compact : styles.regular, style]}>{children}</View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    ...cardShadow,
  },
  regular: { padding: space.lg },
  compact: { padding: space.md },
});
