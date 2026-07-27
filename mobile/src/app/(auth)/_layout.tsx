/**
 * The signed-out stack.
 *
 * Everything under `(auth)` is reachable only while `status` is
 * `unauthenticated`; the redirect in the root layout enforces that.
 */

import { Stack } from 'expo-router';

import { color } from '@/theme/tokens';

export default function AuthLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: color.paper },
      }}
    />
  );
}
