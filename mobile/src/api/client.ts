/**
 * HTTP client.
 *
 * Phase 3 replaces the hand-written response types with a TypeScript client
 * generated from the backend's OpenAPI schema, so a change to a response shape
 * becomes a compile error here. This module — base URL resolution, timeouts,
 * error classification, token refresh — stays, because generated clients do none
 * of that.
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
    (Constants.expoGoConfig as { debuggerHost?: string } | undefined)?.debuggerHost;

  const host = hostUri?.split(':')[0];
  if (host) return `http://${host}:${API_PORT}`;

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
  /** `detail` from the backend's error body, when it sent one. */
  readonly detail?: string;

  constructor(kind: ApiErrorKind, message: string, status?: number, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }

  /** Copy suitable for showing a user directly. */
  get userMessage(): string {
    if (this.detail) return this.detail;
    switch (this.kind) {
      case 'timeout':
        return 'The server took too long to respond. Check your connection and try again.';
      case 'network':
        return 'Could not reach the server. Check your connection and try again.';
      case 'parse':
        return 'The server sent something unexpected. Try again in a moment.';
      default:
        return 'Something went wrong on the server. Try again in a moment.';
    }
  }
}

/* -------------------------------------------------------------------------- */
/* Auth wiring                                                                */
/* -------------------------------------------------------------------------- */

interface AuthHooks {
  getAccessToken: () => string | null;
  /** Exchange the refresh token; returns the new access token, or null if the session is over. */
  refreshSession: () => Promise<string | null>;
  /** Called when the session cannot be recovered, so the app can send the user to login. */
  onSessionExpired: () => void;
}

let authHooks: AuthHooks | null = null;

/**
 * Registered by the auth provider on mount.
 *
 * Inversion of control, deliberately: if this module imported the auth context
 * directly, and the auth context imports this module to make requests, the two
 * would form an import cycle — which in Metro resolves to one of them being
 * `undefined` at runtime, in a way that is very hard to diagnose.
 */
export function configureAuth(hooks: AuthHooks): void {
  authHooks = hooks;
}

/**
 * Single-flight refresh.
 *
 * When an access token expires, every in-flight request fails with 401 at
 * roughly the same moment. Without this, each one would independently call
 * /auth/refresh — and because the backend *rotates* refresh tokens, the first
 * call invalidates the token the others are still holding. They would then be
 * treated as replayed tokens, trigger the theft response, and log the user out
 * of every device. The bug would look completely random.
 *
 * Holding one shared promise means concurrent 401s all await the same refresh.
 */
let inFlightRefresh: Promise<string | null> | null = null;

function refreshOnce(): Promise<string | null> {
  if (!authHooks) return Promise.resolve(null);
  inFlightRefresh ??= authHooks.refreshSession().finally(() => {
    inFlightRefresh = null;
  });
  return inFlightRefresh;
}

/* -------------------------------------------------------------------------- */
/* Requests                                                                   */
/* -------------------------------------------------------------------------- */

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Attach the access token and retry once after refreshing on a 401. */
  authenticated?: boolean;
  timeoutMs?: number;
}

async function rawRequest(
  path: string,
  { method = 'GET', body, timeoutMs = DEFAULT_TIMEOUT_MS }: RequestOptions,
  accessToken: string | null,
): Promise<Response> {
  const url = `${resolveApiBaseUrl()}${path}`;

  // AbortController rather than racing a promise: this actually cancels the
  // in-flight request instead of leaving it running and ignoring the result.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  try {
    return await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    const aborted = controller.signal.aborted;
    throw new ApiError(
      aborted ? 'timeout' : 'network',
      aborted ? `Request to ${url} timed out after ${timeoutMs}ms` : `Could not reach ${url}`,
    );
  } finally {
    clearTimeout(timer);
  }
}

async function parseBody<T>(response: Response, url: string): Promise<T> {
  // 204 has no body by definition, and calling .json() on it throws.
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError('parse', `Response from ${url} was not valid JSON`);
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  // FastAPI puts a human-readable message in `detail`. Surfacing it is what lets
  // the UI say "An account with this email already exists" rather than "409".
  let detail: string | undefined;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') detail = body.detail;
  } catch {
    // Non-JSON error body. Fall back to the generic message.
  }
  return new ApiError(
    'http',
    `${response.status} ${response.statusText}`,
    response.status,
    detail,
  );
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const wantsAuth = options.authenticated ?? false;
  let token = wantsAuth ? (authHooks?.getAccessToken() ?? null) : null;

  let response = await rawRequest(path, options, token);

  if (response.status === 401 && wantsAuth) {
    // The access token is short-lived by design, so a 401 here is expected
    // routine, not an error. Refresh and retry once — never in a loop, because a
    // genuinely rejected session would spin forever.
    token = await refreshOnce();
    if (token === null) {
      authHooks?.onSessionExpired();
      throw new ApiError('http', 'Session expired', 401);
    }
    response = await rawRequest(path, options, token);
  }

  if (!response.ok) throw await toApiError(response);
  return parseBody<T>(response, path);
}

/** Convenience wrapper for unauthenticated GETs, e.g. the health check. */
export function apiGet<T>(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  return apiRequest<T>(path, { method: 'GET', timeoutMs });
}
