/**
 * Root layout — the shell every screen renders inside.
 *
 * expo-router uses *file-based routing*: the file tree under `src/app` defines
 * the navigation tree. A folder in parentheses like `(auth)` is a **route
 * group** — it organises files without appearing in the URL, so `(auth)/login`
 * is just `/login`. That is what lets us keep two entirely separate stacks,
 * signed-in and signed-out, and swap between them.
 *
 * Note on imports: expo-router forked React Navigation and no longer re-exports
 * it. `Stack` comes from `expo-router`, never from `@react-navigation/*`.
 */

import { useFonts } from 'expo-font';
import { Stack, useRouter, useSegments } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from '@/auth/context';
import { HOME } from '@/routes';
import { color } from '@/theme/tokens';
import { fontAssets } from '@/theme/typography';

// Must be called at module scope: inside a component it would run after the
// splash screen has already auto-hidden, which is too late to hold it.
SplashScreen.preventAutoHideAsync().catch(() => {
  // Already hidden, or the module re-evaluated during Fast Refresh.
});

/**
 * Sends the user to the right stack whenever the session changes.
 *
 * This is the "automatic redirect" the app needs, and it lives in one effect
 * rather than being a check inside every screen. A per-screen guard has to be
 * remembered on every new screen, and the one that gets forgotten is the leak.
 */
function useProtectedRoute() {
  const { status } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    // Do nothing until the session is known. Redirecting during `loading` is
    // what causes the login screen to flash on every launch for a signed-in
    // user, because at that moment we have not finished reading SecureStore.
    if (status === 'loading') return;

    const inAuthGroup = segments[0] === '(auth)';

    if (status === 'unauthenticated' && !inAuthGroup) {
      router.replace('/login');
    } else if (status === 'authenticated' && inAuthGroup) {
      // `replace`, not `push`: the login screen must not remain on the back
      // stack, or Android's back gesture returns to it after signing in.
      router.replace(HOME);
    }
  }, [status, segments, router]);
}

function RootNavigator() {
  const { status } = useAuth();
  const [fontsLoaded, fontError] = useFonts(fontAssets);

  useProtectedRoute();

  const ready = (fontsLoaded || fontError) && status !== 'loading';

  useEffect(() => {
    if (ready) SplashScreen.hideAsync().catch(() => {});
  }, [ready]);

  // Holding the splash until the session is resolved as well as the fonts is
  // what makes launch look decided rather than indecisive: the user sees the
  // splash, then the correct screen, never a wrong screen being corrected.
  if (!ready) return null;

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: color.paper },
      }}
    />
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <AuthProvider>
        <RootNavigator />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
