/**
 * Motion primitives.
 *
 * Four pieces, each solving one problem, all built on Reanimated so the
 * animation runs on the UI thread and keeps going while JavaScript is busy
 * parsing an API response. That last point is the whole reason to use
 * Reanimated over `Animated`: the moments an app most needs to feel alive are
 * exactly the moments its JS thread is blocked.
 *
 * The house style, applied consistently:
 *
 * * **Short.** Feedback, not entertainment. Past ~300ms an interaction reads
 *   slow rather than smooth, and the user meets it fifty times a week.
 * * **Decelerating.** Fast off the mark, easing into rest. Linear reads
 *   mechanical; bouncing overshoots values people are trying to read.
 * * **Once.** Entrances play on mount, not on every re-render, so a refetch
 *   does not make the screen flicker back to life.
 */

import { type ReactNode, useEffect, useState } from 'react';
import { Pressable, type PressableProps, type StyleProp, Text, type TextStyle } from 'react-native';
import Animated, {
  Easing,
  FadeInDown,
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

import { duration } from '@/theme/tokens';

/* -------------------------------------------------------------------------- */
/* Count-up numbers                                                           */
/* -------------------------------------------------------------------------- */

/**
 * A number that counts to its value instead of appearing at it.
 *
 * Used for the figures that answer the question the user opened the app with —
 * calories left, a macro total. Watching 0 → 1,240 makes the value feel
 * computed for you now; the same digits rendered instantly feel stored.
 *
 * Deliberately not used everywhere. A list of twenty entries all counting at
 * once is noise, and a number that changes as you read it is worse than one
 * that was simply there.
 */
export function CountUp({
  value,
  style,
  format = (n) => Math.round(n).toLocaleString(),
  duration: ms = duration.gentle,
}: {
  value: number;
  style?: StyleProp<TextStyle>;
  format?: (value: number) => string;
  duration?: number;
}) {
  // Held in React state rather than driven through an animated prop, because
  // the value has to be *formatted* — thousands separators, rounding — and that
  // is string work a worklet cannot do.
  //
  // Starts at 0, not at `value`. Seeding it with the target made the first
  // render already correct, so the effect below saw a delta of zero and
  // returned — the number never counted once, on the one render where counting
  // is the entire point. Subsequent updates still animate from wherever the
  // display had got to, which is what makes a changing total look continuous.
  const [shown, setShown] = useState(0);

  useEffect(() => {
    const from = shown;
    const delta = value - from;
    if (delta === 0) return;

    const started = Date.now();
    const timer = setInterval(() => {
      const elapsed = Date.now() - started;
      if (elapsed >= ms) {
        setShown(value);
        clearInterval(timer);
        return;
      }
      // Same decelerating curve as the rings, so a number and the ring beside
      // it arrive together rather than racing.
      const t = elapsed / ms;
      setShown(from + delta * (1 - (1 - t) ** 3));
    }, 16);

    return () => clearInterval(timer);
    // `shown` is intentionally not a dependency: including it would restart the
    // count on every frame it sets.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, ms]);

  return <Text style={style}>{format(shown)}</Text>;
}

/* -------------------------------------------------------------------------- */
/* Press feedback                                                             */
/* -------------------------------------------------------------------------- */

/**
 * A pressable that springs slightly inward while held.
 *
 * Scale rather than opacity. A fading control reads as *disabling itself* under
 * your thumb; one that presses in reads as a physical button accepting the
 * touch — and on a card-heavy interface, opacity also washes out the content
 * you are pressing.
 */
const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export function PressableScale({
  children,
  style,
  scaleTo = 0.97,
  ...props
}: PressableProps & { children: ReactNode; scaleTo?: number }) {
  const scale = useSharedValue(1);

  const animatedStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  return (
    // One element, not a Pressable inside an Animated.View. The wrapper version
    // silently breaks absolute positioning: `position: absolute` on the inner
    // Pressable resolves against the wrapper rather than the screen, so the
    // floating action button lands wherever the wrapper happened to sit in the
    // flow. Animating the Pressable itself keeps the caller's style on the
    // element the caller expects it to be on.
    <AnimatedPressable
      {...props}
      onPressIn={(event) => {
        cancelAnimation(scale);
        // Stiff and barely damped: the press must land instantly, because any
        // lag here is felt as the app being slow rather than smooth.
        scale.value = withSpring(scaleTo, { damping: 18, stiffness: 420 });
        props.onPressIn?.(event);
      }}
      onPressOut={(event) => {
        cancelAnimation(scale);
        scale.value = withSpring(1, { damping: 16, stiffness: 340 });
        props.onPressOut?.(event);
      }}
      style={[style as StyleProp<import('react-native').ViewStyle>, animatedStyle]}
    >
      {children}
    </AnimatedPressable>
  );
}

/* -------------------------------------------------------------------------- */
/* Entrances                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Fades and lifts a card into place, staggered by its position in a list.
 *
 * The stagger is what makes a screen assemble rather than blink. Capped at six
 * steps: beyond that the last card in a long list would wait most of a second
 * for no benefit, and the user scrolling fast would meet cards mid-entrance.
 */
export function EnterUp({
  index = 0,
  children,
  style,
}: {
  index?: number;
  children: ReactNode;
  style?: StyleProp<import('react-native').ViewStyle>;
}) {
  return (
    <Animated.View
      style={style}
      entering={FadeInDown.delay(Math.min(index, 6) * 45)
        .duration(duration.quick)
        .easing(Easing.out(Easing.cubic))}
    >
      {children}
    </Animated.View>
  );
}

/* -------------------------------------------------------------------------- */
/* Animated bar fill                                                          */
/* -------------------------------------------------------------------------- */

/** A horizontal bar that grows to its fraction. Used by the macro bars. */
export function GrowBar({
  fraction,
  tint,
  height = 8,
  radius = 999,
}: {
  fraction: number;
  tint: string;
  height?: number;
  radius?: number;
}) {
  const width = useSharedValue(0);
  const target = Math.max(0, Math.min(1, fraction));

  useEffect(() => {
    width.value = withTiming(target, {
      duration: duration.gentle,
      easing: Easing.out(Easing.cubic),
    });
  }, [target, width]);

  const animatedStyle = useAnimatedStyle(() => ({ width: `${width.value * 100}%` }));

  return (
    <Animated.View
      style={[{ height, borderRadius: radius, backgroundColor: tint }, animatedStyle]}
    />
  );
}
