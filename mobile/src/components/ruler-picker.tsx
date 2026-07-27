/**
 * A horizontal ruler for picking a number by scrolling.
 *
 * **Why a scroll view rather than a slider.**
 *
 * A slider maps the whole range onto the screen's width, so on a 100–250 cm
 * height range one pixel is roughly a centimetre and hitting an exact value is
 * luck. A ruler keeps a fixed pixel spacing per tick and lets the *content*
 * scroll, so precision does not depend on the range — picking 173 from a
 * hundred-value span is as easy as picking it from a ten-value one.
 *
 * It also matches how physical scales read, which is why fitness apps converged
 * on this control: the number is large and central, and the ticks give a sense
 * of where you are without needing labels on every one.
 */

import { useEffect, useRef } from 'react';
import {
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { color, radius, space } from '@/theme/tokens';
import { fontFamily, text } from '@/theme/typography';

const TICK_SPACING = 12;
const TICK_HEIGHT_MINOR = 16;
const TICK_HEIGHT_MAJOR = 30;
const RULER_HEIGHT = 62;

interface RulerPickerProps {
  min: number;
  max: number;
  value: number;
  onChange: (value: number) => void;
  /** Ticks labelled and drawn tall. 10 means every tenth value is a landmark. */
  majorEvery?: number;
  /** Rendered under the value, e.g. "cm". Omitted when the caller formats it. */
  unit?: string;
  /** Overrides the big number, for values that need composing ("5ft, 6in"). */
  formatValue?: (value: number) => string;
  /** Marks one value on the scale, e.g. current weight under a target picker. */
  reference?: { value: number; label: string };
}

export function RulerPicker({
  min,
  max,
  value,
  onChange,
  majorEvery = 10,
  unit,
  formatValue,
  reference,
}: RulerPickerProps) {
  const scrollRef = useRef<ScrollView>(null);
  // Guards the initial scroll-to-position, which would otherwise fire onChange
  // with the value it was just given and fight whatever the parent set.
  const settled = useRef(false);

  const ticks = Math.round(max - min) + 1;
  const contentWidth = (ticks - 1) * TICK_SPACING;

  useEffect(() => {
    if (settled.current) return;
    settled.current = true;
    // Without the frame delay the ScrollView has not laid out and the offset is
    // silently ignored, leaving every picker showing its minimum.
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ x: (value - min) * TICK_SPACING, animated: false });
    });
  }, [value, min]);

  function handleScroll(event: NativeSyntheticEvent<NativeScrollEvent>) {
    const next = Math.round(event.nativeEvent.contentOffset.x / TICK_SPACING) + min;
    const clamped = Math.min(max, Math.max(min, next));
    if (clamped !== value) onChange(clamped);
  }

  return (
    <View>
      <View style={styles.readout}>
        <Text style={styles.value}>{formatValue ? formatValue(value) : Math.round(value)}</Text>
        {unit && !formatValue && <Text style={styles.unit}>{unit}</Text>}
      </View>

      <View style={styles.rulerWrap}>
        <ScrollView
          ref={scrollRef}
          horizontal
          showsHorizontalScrollIndicator={false}
          // Snapping to the tick pitch is what makes every value reachable and
          // makes the control feel like a dial rather than a free scroll.
          snapToInterval={TICK_SPACING}
          decelerationRate="fast"
          onScroll={handleScroll}
          scrollEventThrottle={16}
          // Half the viewport of padding at each end, so the first and last
          // ticks can reach the centre line.
          contentContainerStyle={styles.rulerContent}
        >
          <View style={{ width: contentWidth, height: RULER_HEIGHT }}>
            {Array.from({ length: ticks }, (_, index) => {
              const tickValue = min + index;
              const major = tickValue % majorEvery === 0;
              return (
                <View key={index} style={[styles.tickColumn, { left: index * TICK_SPACING }]}>
                  <View
                    style={[
                      styles.tick,
                      { height: major ? TICK_HEIGHT_MAJOR : TICK_HEIGHT_MINOR },
                      major && styles.tickMajor,
                    ]}
                  />
                  {major && <Text style={styles.tickLabel}>{tickValue}</Text>}
                </View>
              );
            })}
          </View>
        </ScrollView>

        {/* The centre line the value is read against. pointerEvents none so it
            never intercepts the drag it is sitting on top of. */}
        <View pointerEvents="none" style={styles.needle} />
      </View>

      {reference && (
        <Text style={styles.reference}>
          {reference.label}: {Math.round(reference.value)}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  readout: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', gap: 4 },
  value: { fontFamily: fontFamily.extraBold, fontSize: 40, color: color.ink, letterSpacing: -1 },
  unit: { ...text.label, fontSize: 18, color: color.inkMuted },
  rulerWrap: { marginTop: space.lg, height: RULER_HEIGHT, justifyContent: 'flex-start' },
  rulerContent: { paddingHorizontal: '50%' },
  tickColumn: { position: 'absolute', alignItems: 'center', width: TICK_SPACING },
  tick: { width: 1.5, backgroundColor: color.inkFaint, borderRadius: radius.pill },
  tickMajor: { backgroundColor: color.inkMuted, width: 2 },
  tickLabel: { ...text.bodyMuted, fontSize: 11, marginTop: space.xs },
  needle: {
    position: 'absolute',
    top: 0,
    left: '50%',
    marginLeft: -1.5,
    width: 3,
    height: TICK_HEIGHT_MAJOR + 6,
    borderRadius: radius.pill,
    backgroundColor: color.ink,
  },
  reference: { ...text.bodyMuted, fontSize: 12, textAlign: 'center', marginTop: space.md },
});
