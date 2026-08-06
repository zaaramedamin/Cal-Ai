/**
 * Authentication state for the whole app, backed by Supabase.
 *
 * One provider owns the session, and every screen reads it through `useAuth()`.
 * The alternative — each screen loading tokens itself — means several components
 * independently deciding whether you are logged in, which is how you end up with
 * a login screen rendering behind a logged-in one.
 *
 * **What Supabase took over.** Storing tokens, refreshing them before they
 * expire, rotating refresh tokens, and detecting a stolen one. All of that used
 * to live here and in `api/client.ts`, and all of it is now `supabase.auth`. The
 * job left is narrower and clearer: watch the session, expose it, and hand the
 * current access token to the API client.
 *
 * The shape of `useAuth()` is unchanged on purpose, so screens that only sign in
 * or out did not have to be rewritten to move providers.
 */

import type { Session } from '@supabase/supabase-js';
import * as Linking from 'expo-linking';
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { configureAuth } from '@/api/client';
import { supabase } from '@/auth/supabase';

/**
 * `loading` is a real state, not a detail.
 *
 * Reading the keystore takes a few hundred milliseconds. Without a distinct
 * loading state the app would default to "logged out", flash the login screen,
 * and then replace it — every single launch, for users who are in fact signed in.
 */
export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

export interface AuthUser {
  id: string;
  email: string;
}

/** What `signUp` produced, which is not always a session. */
export type SignUpOutcome =
  /** Signed in immediately — the project has email confirmation switched off. */
  | { kind: 'signed-in' }
  /**
   * Supabase sent a confirmation email and the account is inert until it is
   * clicked. The screen has to say so, or the user sits looking at a form that
   * appeared to work and did nothing.
   */
  | { kind: 'confirm-email'; email: string };

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<SignUpOutcome>;
  signOut: () => Promise<void>;
  requestPasswordReset: (email: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function toUser(session: Session | null): AuthUser | null {
  if (!session?.user) return null;
  return { id: session.user.id, email: session.user.email ?? '' };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<AuthUser | null>(null);

  // A ref, not state, because the API client needs the token *synchronously*
  // while building a request. Reading it from state would hand out whatever
  // value was captured at the last render, which after a refresh is the token
  // that has just been replaced.
  const accessToken = useRef<string | null>(null);

  const apply = useCallback((session: Session | null) => {
    accessToken.current = session?.access_token ?? null;
    setUser(toUser(session));
    setStatus(session ? 'authenticated' : 'unauthenticated');
  }, []);

  /* ---- watch the session ---------------------------------------------- */

  useEffect(() => {
    let cancelled = false;

    // The session already on the device, if any. Supabase validates and
    // refreshes it as part of this call, so a token that expired while the app
    // was closed is renewed rather than rejected.
    void supabase.auth.getSession().then(({ data }) => {
      if (!cancelled) apply(data.session);
    });

    // Every subsequent change: sign-in, sign-out, token refresh, and the account
    // being deleted server-side. Subscribing rather than polling is what keeps
    // `accessToken.current` correct after a background refresh — the previous
    // implementation had to notice a 401, refresh by hand, and retry.
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!cancelled) apply(session);
    });

    return () => {
      cancelled = true;
      subscription.subscription.unsubscribe();
    };
  }, [apply]);

  /* ---- wire the API client -------------------------------------------- */

  useEffect(() => {
    configureAuth({
      getAccessToken: () => accessToken.current,

      refreshSession: async () => {
        // Supabase refreshes on its own schedule, so reaching here means a
        // request got a 401 with a token we believed was good — a session
        // revoked server-side, or clock skew. Asking once is worth it; the
        // listener above applies whatever comes back.
        const { data, error } = await supabase.auth.refreshSession();
        if (error || !data.session) return null;
        return data.session.access_token;
      },

      onSessionExpired: () => {
        void supabase.auth.signOut();
      },
    });
  }, []);

  /* ---- actions --------------------------------------------------------- */

  // Errors deliberately propagate to the calling screen, which is what shows the
  // message. Swallowing them here would leave the form with no way to tell the
  // user their password was wrong.

  const signIn = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    if (error) throw error;
  }, []);

  const signUp = useCallback(async (email: string, password: string): Promise<SignUpOutcome> => {
    const trimmed = email.trim();
    const { data, error } = await supabase.auth.signUp({ email: trimmed, password });
    if (error) throw error;

    // No session means the project requires email confirmation. This is the case
    // that silently does nothing if the screen ignores it: the call succeeded,
    // the account exists, and the user still cannot sign in.
    if (!data.session) return { kind: 'confirm-email', email: trimmed };
    return { kind: 'signed-in' };
  }, []);

  const signOut = useCallback(async () => {
    // The listener sets the state; nothing to do here but ask. A failure is
    // ignored on purpose — the user expects to be signed out either way, and
    // Supabase clears the local session even when the network call fails.
    await supabase.auth.signOut();
  }, []);

  const requestPasswordReset = useCallback(async (email: string) => {
    // `redirectTo` is what makes the emailed link come back into *this app*
    // rather than opening a web page. It resolves to `calai://reset-password`
    // in a build and to the Expo Go URL in development, so the same code works
    // in both — hardcoding the scheme would break every development run.
    //
    // The URL must also be listed under Authentication -> URL Configuration in
    // the Supabase dashboard; anything not on that allowlist is silently
    // replaced with the site URL, and the link then opens a browser instead.
    const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
      redirectTo: Linking.createURL('/reset-password'),
    });
    if (error) throw error;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, signIn, signUp, signOut, requestPasswordReset }),
    [status, user, signIn, signUp, signOut, requestPasswordReset],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    // A clear error beats the confusing downstream one you would otherwise get
    // from destructuring null.
    throw new Error('useAuth must be used inside an AuthProvider');
  }
  return context;
}
