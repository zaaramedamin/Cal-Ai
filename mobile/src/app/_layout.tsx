/**
 * Root layout — the shell every screen renders inside.
 *
 * expo-router uses *file-based routing*: the file tree under `src/app` defines
 * the navigation tree. `index.tsx` is `/`, and a `_layout.tsx` wraps everything
 * beside and below it. So this file is where app-wide concerns belong — fonts,
 * providers, the status bar — and they run once rather than being repeated in
 * every screen.
 *
 * Note on imports: expo-router forked React Navigation and no longer re-exports
 * it. `Stack` comes from `expo-router`, never from `@react-navigation/*`. Most
 * tutorials still show the old import and it will not work here.
 */

import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { color } from '@/theme/tokens';
import { fontAssets } from '@/theme/typography';

// Must be called at module scope: inside a component it would run after the
// splash screen has already auto-hidden, which is too late to hold it.
//
// Holding matters because without it the app paints immediately in the system
// font and then reflows when Fraunces and Inter arrive — a visible flash of the
// wrong typeface with every line of text shifting. A brief hold is far less
// noticeable than the reflow.
SplashScreen.preventAutoHideAsync().catch(() => {
  // Already hidden, or the module re-evaluated during Fast Refresh. Nothing to
  // recover, and not worth crashing the app over.
});

export default function RootLayout() {
  // Runtime font loading rather than the expo-font config plugin. The plugin is
  // what Expo recommends and is more efficient, but it embeds fonts at native
  // build time, which requires a prebuild — and prebuilt native code cannot run
  // in Expo Go. Expo Go is our test path, so runtime loading is the option that
  // actually works. Worth revisiting in Phase 7 when we produce real builds.
  const [fontsLoaded, fontError] = useFonts(fontAssets);

  useEffect(() => {
    if (fontsLoaded || fontError) {
      SplashScreen.hideAsync().catch(() => {});
    }
  }, [fontsLoaded, fontError]);

  // `fontError` deliberately lets the app through instead of blocking. A font
  // that fails to decode should degrade to the system typeface, not strand the
  // user on a splash screen forever with no way forward.
  if (!fontsLoaded && !fontError) return null;

  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: color.paper },
        }}
      />
    </SafeAreaProvider>
  );
}
