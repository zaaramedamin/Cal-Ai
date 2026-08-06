/**
 * The banner at the top of the sign-in and sign-up screens.
 *
 * **It shows the product, not a mood.** The first version was a gradient with a
 * logo on it — the visual equivalent of saying nothing. This one puts a working
 * calorie ring and real macro chips on a dark field, so the first thing someone
 * sees is what the app actually does. Fintech and fitness apps converged on this
 * for a reason: a preview of the interface answers "what is this" before the
 * strapline gets a chance to.
 *
 * **The photograph is a layer, not the design.** When `auth-hero.jpg` exists it
 * sits behind everything, darkened by a scrim; when it does not, the panel is
 * exactly what it was before. That ordering matters: the composition has to hold
 * up on a fresh clone with no assets, and white text over an unknown photograph
 * is a legibility risk that only shows up on the one image nobody tested. The
 * scrim is what makes any photograph safe here rather than hoping for a dark
 * one.
 *
 * The numbers are illustrative and chosen to look like a real day rather than a
 * round advertisement: 1,847 of a 2,200 target, with macros that actually sum to
 * roughly that. A demo showing 2,000 / 2,000 reads as a mock-up.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { Image, StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

import { useT } from '@/i18n';
import { Wordmark } from '@/components/wordmark';
import { photo } from '@/theme/imagery';
import { color, radius, space } from '@/theme/tokens';
import { fontFamily, text } from '@/theme/typography';

/** A plausible day, not a round number. See the module note. */
const DEMO = { eaten: 1847, target: 2200, protein: 132, carbs: 198, fat: 61 };

export function AuthHero({ strapline }: { strapline: string }) {
  const t = useT();
  const progress = DEMO.eaten / DEMO.target;
  const backdrop = photo('authHero');

  return (
    <View style={styles.wrap}>
      {backdrop && (
        <>
          <Image source={backdrop} style={StyleSheet.absoluteFill} resizeMode="cover" />
          {/* Two layers, not one. A flat overlay at the strength needed to make
              the wordmark legible also flattens the photograph into grey mud;
              a gradient keeps the image readable at the top where there is no
              text and goes dense at the bottom where the card sits. */}
          <Svg style={StyleSheet.absoluteFill} width="100%" height="100%" viewBox="0 0 400 300">
            <Defs>
              <LinearGradient id="scrim" x1="0" y1="0" x2="0" y2="1">
                <Stop offset="0" stopColor={color.ink} stopOpacity="0.45" />
                <Stop offset="0.5" stopColor={color.ink} stopOpacity="0.65" />
                <Stop offset="1" stopColor={color.ink} stopOpacity="0.88" />
              </LinearGradient>
            </Defs>
            <Rect x="0" y="0" width="400" height="300" fill="url(#scrim)" />
          </Svg>
        </>
      )}
      {/* A soft indigo bloom rather than a linear gradient. A top-to-bottom ramp
          reads as a template; an off-centre glow gives the panel a light source
          and lets the card below look like it is sitting in front of something. */}
      <Svg style={StyleSheet.absoluteFill} width="100%" height="100%" viewBox="0 0 400 300">
        <Defs>
          <LinearGradient id="bloom" x1="0.15" y1="0" x2="0.9" y2="1">
            <Stop offset="0" stopColor={color.accent} stopOpacity="0.55" />
            <Stop offset="0.55" stopColor={color.accentDeep} stopOpacity="0.22" />
            <Stop offset="1" stopColor={color.ink} stopOpacity="0" />
          </LinearGradient>
        </Defs>
        {/* Only when there is no photograph — otherwise this opaque fill would
            hide it entirely. The bloom stays either way: over an image it reads
            as a coloured light source rather than a gradient. */}
        {!backdrop && <Rect x="0" y="0" width="400" height="300" fill={color.ink} />}
        <Rect x="0" y="0" width="400" height="300" fill="url(#bloom)" />
      </Svg>

      <View style={styles.content}>
        <Wordmark size={26} onDark />
        <Text style={styles.strapline}>{strapline}</Text>

        {/* The preview card. Deliberately overlaps the panel's bottom edge so it
            bridges the hero and the form, tying the two halves of the screen
            together instead of stacking two unrelated blocks. */}
        <View style={styles.card}>
          <View style={styles.cardLeft}>
            <Text style={styles.cardValue}>{(DEMO.target - DEMO.eaten).toLocaleString()}</Text>
            <Text style={styles.cardLabel}>{t('home.caloriesLeft')}</Text>
            <View style={styles.chips}>
              <Chip tint={color.protein} grams={DEMO.protein} />
              <Chip tint={color.carbs} grams={DEMO.carbs} />
              <Chip tint={color.fat} grams={DEMO.fat} />
            </View>
          </View>

          {/* Drawn directly rather than reusing ProgressRing, because that
              component animates on mount and this is furniture — a ring
              sweeping every time the login screen mounts would draw the eye to
              the wrong thing. */}
          <Svg width={72} height={72} style={styles.ring}>
            <Circle cx={36} cy={36} r={30} stroke={color.wash} strokeWidth={8} fill="none" />
            <Circle
              cx={36}
              cy={36}
              r={30}
              stroke={color.accent}
              strokeWidth={8}
              fill="none"
              strokeLinecap="round"
              strokeDasharray={2 * Math.PI * 30}
              strokeDashoffset={2 * Math.PI * 30 * (1 - progress)}
            />
          </Svg>
          <Ionicons name="flame" size={20} color={color.accent} style={styles.ringIcon} />
        </View>
      </View>
    </View>
  );
}

function Chip({ tint, grams }: { tint: string; grams: number }) {
  return (
    <View style={styles.chip}>
      <View style={[styles.chipDot, { backgroundColor: tint }]} />
      <Text style={styles.chipText}>{grams}g</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    // Must match `Screen`'s own padding — `space.xl` horizontally, and the
    // `space.lg` it adds below the safe-area inset — or the bleed leaves a
    // hairline of canvas down one side.
    marginHorizontal: -space.xl,
    marginTop: -space.lg,
    paddingTop: space.xxl,
    // Room for the card to hang past the bottom edge.
    paddingBottom: 54,
    borderBottomLeftRadius: radius.xl,
    borderBottomRightRadius: radius.xl,
    backgroundColor: color.ink,
  },
  content: { paddingHorizontal: space.xl, gap: space.sm },
  strapline: {
    ...text.body,
    color: 'rgba(255, 255, 255, 0.72)',
    fontSize: 14,
    lineHeight: 20,
    maxWidth: 270,
    marginBottom: space.lg,
  },

  card: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    padding: space.lg,
    // Hangs below the panel, overlapping into the form area.
    marginBottom: -84,
  },
  cardLeft: { gap: 2 },
  cardValue: {
    fontFamily: fontFamily.extraBold,
    fontSize: 34,
    letterSpacing: -1,
    color: color.ink,
  },
  cardLabel: { ...text.bodyMuted, fontSize: 12 },
  chips: { flexDirection: 'row', gap: space.md, marginTop: space.sm },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  chipDot: { width: 7, height: 7, borderRadius: radius.pill },
  chipText: { ...text.numeric, fontSize: 12, color: color.inkMuted },

  ring: { transform: [{ rotate: '-90deg' }] },
  // Centred over the ring by hand: the ring is rotated, so a child of it would
  // be rotated too.
  ringIcon: { position: 'absolute', right: space.lg + 26, top: '50%', marginTop: -10 },
});
