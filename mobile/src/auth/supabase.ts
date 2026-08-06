/**
 * The Supabase client, configured for React Native.
 *
 * Four settings below are not defaults, and each one is wrong by default in a
 * native app:
 *
 * * **`storage`** — sessions go to the device keystore, chunked. See
 *   `storage.ts`; without it, Supabase reaches for `localStorage`, which does
 *   not exist here, and the session is lost on every app restart.
 * * **`detectSessionInUrl: false`** — that behaviour reads an OAuth callback out
 *   of `window.location`. There is no URL bar in a native app, and leaving it on
 *   makes the client touch `window` on a platform that has no such thing.
 * * **`autoRefreshToken: true`** with an explicit AppState hook below. Supabase
 *   refreshes on a timer, and timers do not fire while an app is backgrounded —
 *   so a phone left in a pocket wakes with an expired token and one failed
 *   request before recovering.
 * * **`persistSession: true`** — the whole point of the keystore work.
 *
 * The URL and key come from `app.config.ts` rather than `process.env` directly,
 * so they are baked into the build and readable through `expo-constants` at
 * runtime. The anon key being in the bundle is expected: Supabase's model
 * assumes an attacker holds it, and access is controlled by token verification
 * and row-level security instead.
 */

// Must be first: supabase-js uses the WHATWG URL API, which React Native's
// Hermes runtime does not implement. Without this the client throws
// "URL.protocol is not implemented" on its very first request.
import 'react-native-url-polyfill/auto';

import { type SupabaseClient, createClient } from '@supabase/supabase-js';
import Constants from 'expo-constants';
import { AppState } from 'react-native';

import { secureSessionStorage } from '@/auth/storage';

const extra = Constants.expoConfig?.extra ?? {};

export const SUPABASE_URL: string = extra.supabaseUrl ?? '';
export const SUPABASE_ANON_KEY: string = extra.supabaseAnonKey ?? '';

/**
 * Whether Supabase Auth is available in this build.
 *
 * Checked rather than assumed because a missing value produces a client that
 * fails on every call with an opaque network error. A screen can ask this and
 * say something true instead.
 */
export const supabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

export const supabase: SupabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: secureSessionStorage,
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
  },
});

/**
 * Refresh while the app is in the foreground, and stop while it is not.
 *
 * Supabase's auto-refresh runs on a JavaScript timer. Backgrounded apps have
 * their timers throttled or suspended by both platforms, so without this the
 * token quietly expires in a pocket and the first tap after unlocking fails.
 * Restarting the loop on foreground makes that a non-event.
 */
AppState.addEventListener('change', (state) => {
  if (state === 'active') {
    void supabase.auth.startAutoRefresh();
  } else {
    void supabase.auth.stopAutoRefresh();
  }
});
