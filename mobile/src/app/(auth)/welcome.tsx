/**
 * The first screen a signed-out person sees.
 *
 * A full-bleed photograph with a card of copy sitting over its lower edge, three
 * slides deep. The shape is the convention for this category, and conventions in
 * a first-run flow are worth following: the user already knows where the dots
 * and the button will be, so all their attention goes to the words.
 *
 * **Why the photo is behind the card rather than above it.** Stacking a picture
 * on top of a panel gives two rectangles meeting at a seam, and the seam is the
 * first thing the eye finds. Letting the card overlap makes the photograph feel
 * like the surface the card is resting on, which is one object instead of two.
 *
 * **Why a ScrollView and not a carousel library.** Three slides, paging, and a
 * dot per slide. `pagingEnabled` does all of it natively, and a dependency here
 * would be a dependency in the first thing that has to load.
 */

import { useRouter } from 'expo-router';
import { useRef, useState } from 'react';
import {
  Image,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/button';
import { Wordmark } from '@/components/wordmark';
import { type Translate, useT } from '@/i18n';
import { type PhotoSlot, photo } from '@/theme/imagery';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

interface Slide {
  slot: PhotoSlot;
  title: string;
  body: string;
}

function slides(t: Translate): Slide[] {
  return [
    { slot: 'onboarding1', title: t('welcome.1Title'), body: t('welcome.1Body') },
    { slot: 'onboarding2', title: t('welcome.2Title'), body: t('welcome.2Body') },
    { slot: 'onboarding3', title: t('welcome.3Title'), body: t('welcome.3Body') },
  ];
}

export default function WelcomeScreen() {
  const router = useRouter();
  const t = useT();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();

  const scroller = useRef<ScrollView>(null);
  const [index, setIndex] = useState(0);

  const deck = slides(t);
  const last = index === deck.length - 1;

  function onScroll(event: NativeSyntheticEvent<NativeScrollEvent>) {
    // Rounding rather than flooring: a drag that settles a pixel short of the
    // boundary would otherwise leave the dots showing the previous slide.
    const next = Math.round(event.nativeEvent.contentOffset.x / width);
    if (next !== index) setIndex(next);
  }

  function advance() {
    if (last) {
      router.push('/register');
      return;
    }
    scroller.current?.scrollTo({ x: width * (index + 1), animated: true });
  }

  return (
    <View style={styles.root}>
      <ScrollView
        ref={scroller}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={onScroll}
        style={StyleSheet.absoluteFill}
      >
        {deck.map((slide) => {
          const image = photo(slide.slot);
          return (
            <View key={slide.slot} style={{ width }}>
              {image ? (
                <Image source={image} style={styles.photo} resizeMode="cover" />
              ) : (
                // The screen has to be presentable on a fresh clone with no
                // assets, so the empty case is a designed panel rather than a
                // grey box — see `theme/imagery.ts`.
                <View style={[styles.photo, styles.photoFallback]} />
              )}
            </View>
          );
        })}
      </ScrollView>

      {/* Outside the ScrollView so it stays put while the photos slide beneath
          it. Inside, the copy would slide with the image and the card would
          have to be repeated three times. */}
      <View style={[styles.sheet, { paddingBottom: insets.bottom + space.lg }]}>
        <Text style={styles.title}>{deck[index].title}</Text>
        <Text style={styles.body}>{deck[index].body}</Text>

        <View style={styles.dots}>
          {deck.map((slide, position) => (
            <View
              key={slide.slot}
              style={[styles.dot, position === index && styles.dotActive]}
            />
          ))}
        </View>

        <Button label={last ? t('welcome.start') : t('welcome.next')} onPress={advance} />

        <Pressable
          onPress={() => router.push('/login')}
          style={styles.signIn}
          hitSlop={8}
          accessibilityRole="button"
        >
          <Text style={text.bodyMuted}>{t('welcome.haveAccount')} </Text>
          <Text style={styles.signInLink}>{t('auth.signIn')}</Text>
        </Pressable>
      </View>

      <View style={[styles.mark, { top: insets.top + space.md }]}>
        <Wordmark size={18} onDark />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.ink },

  // 62% leaves the photograph dominant while keeping three lines of body copy
  // clear of the fold on a small phone. The sheet overlaps it, so the visible
  // portion is smaller than this number suggests.
  photo: { width: '100%', height: '62%' },
  photoFallback: { backgroundColor: color.wash },

  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: color.canvas,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: space.lg,
    paddingTop: space.xl,
    gap: space.md,
    minHeight: '42%',
  },
  title: { ...text.title, textAlign: 'center' },
  body: { ...text.bodyMuted, textAlign: 'center', lineHeight: 22 },

  dots: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: space.xs,
    marginTop: 'auto',
    marginBottom: space.md,
  },
  // inkFaint, not wash: at 5% the inactive dots were a 1.05:1 smudge on the
  // canvas, so the carousel never showed there was more than one slide.
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: color.inkFaint },
  dotActive: { backgroundColor: color.accent, width: 20 },

  signIn: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center' },
  signInLink: { ...text.label, color: color.accent },

  mark: { position: 'absolute', left: space.lg },
});
