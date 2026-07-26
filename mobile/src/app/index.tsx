/**
 * Phase 0 connection check.
 *
 * This screen exists to prove the whole pipe works — phone → API → Postgres —
 * before a single feature is built. Its purpose is temporary; its quality is
 * not. It already uses the design tokens, and it already has the three designed
 * states every screen in this app is required to have.
 *
 * The hero number is the round-trip time. On a screen about connectivity that is
 * genuinely the most useful number on it, and it gives the tabular numerals
 * something real to do.
 */

import { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError, resolveApiBaseUrl } from '@/api/client';
import { getHealth, type Health } from '@/api/health';
import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { StatusRow } from '@/components/status-row';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

type Phase =
  | { kind: 'loading' }
  | { kind: 'ready'; health: Health; latencyMs: number }
  | { kind: 'failed'; error: ApiError };

export default function ConnectionCheckScreen() {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const baseUrl = resolveApiBaseUrl();

  const check = useCallback(async () => {
    setPhase({ kind: 'loading' });
    const startedAt = Date.now();
    try {
      const health = await getHealth();
      setPhase({ kind: 'ready', health, latencyMs: Date.now() - startedAt });
    } catch (caught) {
      const error =
        caught instanceof ApiError
          ? caught
          : new ApiError('network', caught instanceof Error ? caught.message : 'Unknown failure');
      setPhase({ kind: 'failed', error });
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={text.overline}>CalAi</Text>
        <Text style={text.title}>Connection check</Text>
        <Text style={[text.bodyMuted, styles.intro]}>
          Phase 0 proves the whole pipe before any features exist: this phone, the FastAPI
          backend, and Postgres behind it.
        </Text>

        {phase.kind === 'loading' && <LoadingState baseUrl={baseUrl} />}
        {phase.kind === 'ready' && (
          <ReadyState health={phase.health} latencyMs={phase.latencyMs} baseUrl={baseUrl} />
        )}
        {phase.kind === 'failed' && <FailedState error={phase.error} baseUrl={baseUrl} />}

        {phase.kind !== 'loading' && (
          <View style={styles.actions}>
            <Button label="Check again" onPress={() => void check()} />
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

/* -------------------------------------------------------------------------- */

function LoadingState({ baseUrl }: { baseUrl: string }) {
  return (
    <View style={styles.card}>
      <StatusRow label="Backend" value="Checking…" tone="pending" />
      <StatusRow label="Database" value="Waiting" tone="pending" />
      <Text style={[text.bodyMuted, styles.footnote]}>Reaching {baseUrl}</Text>
    </View>
  );
}

function ReadyState({
  health,
  latencyMs,
  baseUrl,
}: {
  health: Health;
  latencyMs: number;
  baseUrl: string;
}) {
  const dbReachable = health.db === 'ok';

  return (
    <>
      <View style={styles.heroBlock}>
        <Text style={text.hero}>{latencyMs}</Text>
        <Text style={text.overline}>ms round trip</Text>
      </View>

      <View style={styles.card}>
        <StatusRow label="Backend" value={`v${health.version}`} tone="good" />
        <StatusRow
          label="Database"
          value={dbReachable ? 'Connected' : 'Unreachable'}
          tone={dbReachable ? 'good' : 'bad'}
        />
        <StatusRow label="Endpoint" value={baseUrl} tone="good" />
      </View>

      {/*
        The backend answered, so this is not a connection failure — it is a
        partial success, and it gets its own treatment rather than being folded
        into the generic error state. Telling the user "the API is fine, the
        database is not" is the difference between a useful message and a shrug.
      */}
      {!dbReachable && (
        <Callout
          title="Postgres isn't reachable"
          lines={[
            'The API is running and answering, but it cannot reach the database.',
            'Start it with:  docker compose up -d',
            'Confirm it came up healthy with:  docker compose ps',
          ]}
        />
      )}
    </>
  );
}

function FailedState({ error, baseUrl }: { error: ApiError; baseUrl: string }) {
  const { title, lines } = describeFailure(error, baseUrl);

  return (
    <>
      <View style={styles.card}>
        <StatusRow label="Backend" value="No response" tone="bad" />
        <StatusRow label="Database" value="Unknown" tone="pending" />
      </View>
      <Callout title={title} lines={lines} />
    </>
  );
}

/**
 * Each failure kind gets advice specific to it. A single "Something went wrong"
 * would be true, useless, and exactly the vague apology the brief rules out.
 */
function describeFailure(error: ApiError, baseUrl: string): { title: string; lines: string[] } {
  switch (error.kind) {
    case 'timeout':
      return {
        title: 'The backend did not answer in time',
        lines: [
          `No reply from ${baseUrl} within 10 seconds.`,
          'It may still be starting, or stuck opening a database connection.',
          'Check the terminal running uvicorn for a traceback.',
        ],
      };
    case 'http':
      return {
        title: `The backend returned ${error.status ?? 'an error'}`,
        lines: [
          'The connection itself worked, so networking is fine — the server failed.',
          'The uvicorn terminal will have the traceback.',
        ],
      };
    case 'parse':
      return {
        title: 'The response was not valid JSON',
        lines: [
          `Something answered at ${baseUrl}, but it was not the CalAi API.`,
          'A captive portal or a proxy on this network causes exactly this.',
        ],
      };
    default:
      return {
        title: 'Cannot reach the backend',
        lines: [
          `Tried ${baseUrl} and got no response at all.`,
          '1.  Is uvicorn running?',
          '2.  Was it started with --host 0.0.0.0 ?  Bound to 127.0.0.1 it refuses this phone.',
          '3.  Is this phone on the same Wi-Fi as the computer?',
          '4.  Windows Firewall blocks inbound port 8000 by default — see the README.',
        ],
      };
  }
}

function Callout({ title, lines }: { title: string; lines: string[] }) {
  return (
    <View style={styles.callout} accessibilityRole="alert">
      <Text style={styles.calloutTitle}>{title}</Text>
      {lines.map((line) => (
        <Text key={line} style={[text.bodyMuted, styles.calloutLine]}>
          {line}
        </Text>
      ))}
    </View>
  );
}

/* -------------------------------------------------------------------------- */

const styles = StyleSheet.create({
  content: {
    paddingBottom: space.xxl,
  },
  intro: {
    marginTop: space.sm,
    marginBottom: space.xl,
  },
  heroBlock: {
    alignItems: 'flex-start',
    marginBottom: space.lg,
  },
  card: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.hairline,
    paddingHorizontal: space.lg,
    paddingVertical: space.xs,
  },
  footnote: {
    paddingVertical: space.md,
    fontSize: 13,
  },
  callout: {
    marginTop: space.lg,
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    // A left rule rather than a filled panel: it reads as "note" at a glance
    // without turning the block into an alarming slab of colour.
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
  actions: {
    marginTop: space.xl,
  },
});
