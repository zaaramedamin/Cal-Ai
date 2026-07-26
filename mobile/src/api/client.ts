/**
 * HTTP client.
 *
 * Phase 3 replaces the hand-written response types below with a TypeScript
 * client generated from the backend's OpenAPI schema, so a change to a response
 * shape becomes a compile error in this app. This module — base URL resolution,
 * timeouts, error classification — stays, because generated clients do not do
 * any of that.
 */

import Constants from 'expo-constants';

/** The port uvicorn is told to bind in the README's run command. */
const API_PORT = 8000;

/** A slow network should surface a designed error, not a spinner that never ends. */
const DEFAULT_TIMEOUT_MS = 10_000;

/**
 * Work out which machine the API is on.
 *
 * This is the single most common thing that goes wrong when a beginner first
 * runs a mobile app against a local backend: `http://localhost:8000` typed into
 * the app means *the phone itself*, which is running no server, so the request
 * is refused. The API has to be addressed by the development machine's LAN IP.
 *
 * Hardcoding that IP works until you join a different network and your router
 * hands out a different address — then the app breaks with no obvious cause. So
 * instead we derive it: Expo Go loaded this bundle from the dev server, and
 * `hostUri` records the host it came from (e.g. `192.168.1.24:8081`). The API is
 * on the same machine, so the same host with port 8000 is the answer, and it
 * re-resolves automatically whenever the IP changes.
 *
 * `EXPO_PUBLIC_API_URL` overrides everything, which is how Phase 7 points a
 * release build at the deployed backend.
 */
export function resolveApiBaseUrl(): string {
  const explicit = process.env.EXPO_PUBLIC_API_URL;
  if (explicit) return explicit.replace(/\/+$/, '');

  const hostUri =
    Constants.expoConfig?.hostUri ??
    // Older/bare-workflow shape; kept as a fallback so this cannot silently
    // return localhost on a setup where only the legacy field is populated.
    (Constants.expoGoConfig as { debuggerHost?: string } | undefined)?.debuggerHost;

  const host = hostUri?.split(':')[0];
  if (host) return `http://${host}:${API_PORT}`;

  // Reached on web, or in a build with no dev server. Correct there, because the
  // browser and the API really are on the same machine.
  return `http://localhost:${API_PORT}`;
}

/**
 * Why the failure is classified rather than thrown as a bare `Error`: the UI has
 * to tell the user what to actually do, and "we couldn't reach the server" needs
 * different advice from "the server said 500". A single opaque error message
 * forces the vague apology the brief rules out.
 */
export type ApiErrorKind = 'network' | 'timeout' | 'http' | 'parse';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;

  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
  }
}

export async function apiGet<T>(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const url = `${resolveApiBaseUrl()}${path}`;

  // AbortController rather than racing a promise: this actually cancels the
  // in-flight request instead of leaving it running and ignoring the result.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
  } catch (cause) {
    const aborted = controller.signal.aborted;
    throw new ApiError(
      aborted ? 'timeout' : 'network',
      aborted ? `Request to ${url} timed out after ${timeoutMs}ms` : `Could not reach ${url}`,
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new ApiError('http', `${response.status} ${response.statusText}`, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError('parse', `Response from ${url} was not valid JSON`);
  }
}
