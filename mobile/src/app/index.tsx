/**
 * Signed-in home.
 *
 * Phase 2 replaces this with onboarding and the daily targets screen. For now it
 * proves the two things Phase 1 is responsible for: that a protected endpoint
 * accepts our token, and that the session survives a full app restart.
 */

import { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { getHealth, type Health } from '@/api/health';
import { useAuth } from '@/auth/context';
import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { StatusRow } from '@/components/status-row';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

type BackendState =
  | { kind: 'checking' }
  | { kind: 'ready'; health: Health }
  | { kind: 'failed'; message: string };

export default function HomeScreen() {
  const { user, signOut } = useAuth();
  const [backend, setBackend] = useState<BackendState>({ kind: 'checking' });
  const [signingOut, setSigningOut] = useState(false);

  const check = useCallback(async () => {
    setBackend({ kind: 'checking' });
    try {
      setBackend({ kind: 'ready', health: await getHealth() });
    } catch (error) {
      setBackend({
        kind: 'failed',
        message: error instanceof ApiError ? error.userMessage : 'Could not reach the server.',
      });
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  const memberSince = user
    ? new Date(user.created_at).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    : '—';

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={text.overline}>Signed in</Text>
        <Text style={text.title}>{user?.email ?? 'Your account'}</Text>
        <Text style={[text.bodyMuted, styles.intro]}>
          Phase 1 is done: your account is real, your session is stored in the device keystore,
          and this screen loaded by calling a protected endpoint with your token.
        </Text>

        <View style={styles.card}>
          <StatusRow label="Account" value={user ? 'Verified' : 'Unknown'} tone={user ? 'good' : 'bad'} />
          <StatusRow label="Member since" value={memberSince} tone="good" />
          {backend.kind === 'checking' && (
            <StatusRow label="Backend" value="Checking…" tone="pending" />
          )}
          {backend.kind === 'ready' && (
            <StatusRow
              label="Backend"
              value={`v${backend.health.version} · db ${backend.health.db}`}
              tone={backend.health.db === 'ok' ? 'good' : 'warn'}
            />
          )}
          {backend.kind === 'failed' && (
            <StatusRow label="Backend" value="Unreachable" tone="bad" />
          )}
        </View>

        {backend.kind === 'failed' && (
          <View style={styles.callout} accessibilityRole="alert">
            <Text style={styles.calloutTitle}>Can&apos;t reach the backend</Text>
            <Text style={[text.bodyMuted, styles.calloutLine]}>{backend.message}</Text>
            <Text style={[text.bodyMuted, styles.calloutLine]}>
              You are still signed in — this only affects loading new data.
            </Text>
          </View>
        )}

        <View style={styles.nextUp}>
          <Text style={text.overline}>Next</Text>
          <Text style={[text.bodyMuted, styles.calloutLine]}>
            Phase 2 collects your body stats and goal, then calculates your daily calorie and
            macro targets — and shows you exactly how the number was derived.
          </Text>
        </View>

        <View style={styles.actions}>
          <Button
            label="Sign out"
            loading={signingOut}
            onPress={() => {
              setSigningOut(true);
              void signOut().finally(() => setSigningOut(false));
            }}
          />
        </View>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingBottom: space.xxl,
  },
  intro: {
    marginTop: space.sm,
    marginBottom: space.xl,
  },
  card: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.hairline,
    paddingHorizontal: space.lg,
    paddingVertical: space.xs,
  },
  callout: {
    marginTop: space.lg,
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.clay,
    gap: space.xs,
  },
  calloutTitle: {
    ...text.label,
    marginBottom: space.xs,
  },
  calloutLine: {
    fontSize: 14,
    lineHeight: 20,
  },
  nextUp: {
    marginTop: space.xl,
    gap: space.sm,
  },
  actions: {
    marginTop: space.xxl,
  },
});
