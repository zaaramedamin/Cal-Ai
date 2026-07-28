/**
 * The banner at the top of the sign-in and sign-up screens.
 *
 * A photograph when one exists, and a designed panel when one does not — not a
 * grey box waiting for art. The fallback is built from the same pieces as the
 * rest of the app (the accent, the macro hues, the chevron) so a fresh clone
 * with no photography still looks like a finished product rather than a
 * placeholder somebody forgot.
 *
 * The gradient scrim is not decoration. White text over an uncontrolled
 * photograph is a coin toss — a bright kitchen worktop will swallow it. Fading
 * the image into the ink at the bottom guarantees the wordmark and the strapline
 * sit on something dark enough to read, whatever the picture turns out to be.
 */

import { Image, StyleSheet, Text, View } from 'react-native';
import Svg, { Defs, LinearGradient, Path, Rect, Stop } from 'react-native-svg';

import { Wordmark } from '@/components/wordmark';
import { photo } from '@/theme/imagery';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export function AuthHero({ strapline, height = 232 }: { strapline: string; height?: number }) {
  const source = photo('authHero');

  return (
    <View style={[styles.wrap, { height }]}>
      {source ? (
        <Image source={source} style={StyleSheet.absoluteFill} resizeMode="cover" />
      ) : (
        <FallbackArt />
      )}

      {/* Sits above either background. Transparent at the top so a photograph
          still reads as a photograph, opaque at the bottom where the type is. */}
      <Svg style={StyleSheet.absoluteFill} width="100%" height="100%">
        <Defs>
          <LinearGradient id="scrim" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color.ink} stopOpacity="0.05" />
            <Stop offset="0.55" stopColor={color.ink} stopOpacity="0.45" />
            <Stop offset="1" stopColor={color.ink} stopOpacity="0.88" />
          </LinearGradient>
        </Defs>
        <Rect x="0" y="0" width="100%" height="100%" fill="url(#scrim)" />
      </Svg>

      <View style={styles.copy}>
        <Wordmark size={30} onDark />
        <Text style={styles.strapline}>{strapline}</Text>
      </View>
    </View>
  );
}

/**
 * The no-photograph state: the app's own mark on a deep indigo field, with the
 * three macro colours as a quiet band. Drawn rather than imported so it costs
 * nothing and cannot go missing.
 */
function FallbackArt() {
  return (
    <Svg style={StyleSheet.absoluteFill} width="100%" height="100%" viewBox="0 0 400 240">
      <Defs>
        <LinearGradient id="field" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor={color.accentDeep} />
          <Stop offset="1" stopColor={color.accent} />
        </LinearGradient>
      </Defs>
      <Rect x="0" y="0" width="400" height="240" fill="url(#field)" />

      {/* The chevron from the app icon, oversized and half off the edge, so it
          reads as a graphic device rather than a logo stranded in a box. */}
      <Path
        d="M232,196 L300,96 L368,196"
        stroke={color.onDark}
        strokeOpacity="0.16"
        strokeWidth="26"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />

      {[
        { x: 0, w: 150, fill: color.protein },
        { x: 150, w: 130, fill: color.carbs },
        { x: 280, w: 120, fill: color.fat },
      ].map((band) => (
        <Rect key={band.x} x={band.x} y={236} width={band.w} height={4} fill={band.fill} />
      ))}
    </Svg>
  );
}

const styles = StyleSheet.create({
  wrap: {
    // Bleeds past the screen's horizontal padding to touch both edges, which is
    // what makes it read as a header rather than a card that happens to be big.
    // Must match `Screen`'s own padding exactly — `space.xl` horizontally and
    // the `space.lg` it adds below the safe-area inset — or the bleed leaves a
    // hairline of canvas down one side.
    marginHorizontal: -space.xl,
    marginTop: -space.lg,
    borderBottomLeftRadius: radius.xl,
    borderBottomRightRadius: radius.xl,
    overflow: 'hidden',
    justifyContent: 'flex-end',
    backgroundColor: color.accentDeep,
  },
  copy: { padding: space.xl, gap: space.xs },
  strapline: {
    ...text.body,
    color: 'rgba(255, 255, 255, 0.88)',
    fontSize: 15,
    lineHeight: 21,
    maxWidth: 280,
  },
});
