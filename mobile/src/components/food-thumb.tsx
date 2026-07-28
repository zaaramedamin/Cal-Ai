/**
 * A food's picture, with the emoji as a real fallback rather than a placeholder.
 *
 * The catalogue's `photo` field is null until an image has been uploaded for
 * that food, and it will be null for a while — photos land after the catalogue
 * itself. So the emoji is not a "loading" state to be replaced later; it is the
 * design working with no image at all, which is why it sits on a tinted disc
 * instead of floating as bare text.
 *
 * A failed image load falls back to the same disc. A broken-image icon in a grid
 * of food looks like a bug even when the network is simply flaky.
 */

import { useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { resolveApiBaseUrl } from '@/api/client';
import { color, radius } from '@/theme/tokens';

interface FoodThumbProps {
  emoji: string;
  /** Filename in the catalogue image store, or null. */
  photo: string | null;
  size?: number;
}

export function FoodThumb({ emoji, photo, size = 44 }: FoodThumbProps) {
  const [failed, setFailed] = useState(false);
  const box = { width: size, height: size, borderRadius: size / 2 };

  if (photo && !failed) {
    return (
      <Image
        source={{ uri: `${resolveApiBaseUrl()}/api/v1/catalogue/photos/${photo}` }}
        style={[styles.image, box]}
        onError={() => setFailed(true)}
        accessibilityIgnoresInvertColors
      />
    );
  }

  return (
    <View style={[styles.disc, box]}>
      {/* Scaled to the disc rather than fixed, so one component serves the
          32px list row and the 52px sheet header without a second variant. */}
      <Text style={{ fontSize: size * 0.52 }}>{emoji}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  image: { backgroundColor: color.wash },
  disc: { alignItems: 'center', justifyContent: 'center', backgroundColor: color.wash },
});
