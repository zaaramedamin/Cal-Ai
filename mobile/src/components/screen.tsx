/**
 * Screen wrapper: safe area, background, consistent horizontal padding.
 *
 * Every screen in the app goes through this. The reason is the notch and the
 * home indicator: `SafeAreaView`'s insets differ per device, and getting them
 * wrong means a title tucked under the camera cutout on one phone and floating
 * oddly on another. Solving it once here is the only way it stays solved.
 */

import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { color, space } from '@/theme/tokens';

interface ScreenProps {
  children: ReactNode;
}

export function Screen({ children }: ScreenProps) {
  const insets = useSafeAreaInsets();

  return (
    <View
      style={[
        styles.root,
        // Padding rather than SafeAreaView so a future scrolling screen can let
        // content pass *under* the inset while keeping its own padding correct.
        { paddingTop: insets.top + space.lg, paddingBottom: insets.bottom + space.lg },
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: color.canvas,
    paddingHorizontal: space.xl,
  },
});
