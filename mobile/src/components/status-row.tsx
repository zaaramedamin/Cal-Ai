/**
 * A labelled row with a state dot — the building block of the connection check.
 *
 * The dot carries state by *colour and position*, and the row always carries a
 * text value too. Colour alone is never the only signal, because roughly 1 in 12
 * men cannot reliably separate the green and the orange.
 */

import { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';

import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export type DotTone = 'good' | 'warn' | 'bad' | 'pending';

const TONE_COLOR: Record<DotTone, string> = {
  good: color.moss,
  warn: color.wheat,
  bad: color.clayDeep,
  pending: color.inkFaint,
};

export function StatusDot({ tone }: { tone: DotTone }) {
  // A pulse, only while pending. Motion that never stops is noise; motion that
  // means "still working" is information.
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (tone !== 'pending') {
      pulse.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 0.25, duration: 620, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 620, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [tone, pulse]);

  return (
    <Animated.View
      style={[styles.dot, { backgroundColor: TONE_COLOR[tone], opacity: pulse }]}
    />
  );
}

interface StatusRowProps {
  label: string;
  value: string;
  tone: DotTone;
}

export function StatusRow({ label, value, tone }: StatusRowProps) {
  return (
    <View style={styles.row}>
      <View style={styles.left}>
        <StatusDot tone={tone} />
        <Text style={text.label}>{label}</Text>
      </View>
      <Text style={styles.value} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.md,
    gap: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.hairline,
  },
  left: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: radius.pill,
  },
  value: {
    ...text.numeric,
    color: color.inkMuted,
    flexShrink: 1,
    textAlign: 'right',
  },
});
