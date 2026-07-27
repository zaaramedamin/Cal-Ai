/**
 * Authentication state for the whole app.
 *
 * One provider owns the session, and every screen reads it through `useAuth()`.
 * The alternative — each screen loading tokens itself — means several components
 * independently deciding whether you are logged in, which is how you end up with
 * a login screen rendering behind a logged-in one.
 */

import { type ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import * as authApi from '@/api/auth';
import { configureAuth } from '@/api/client';
import { clearTokens, loadTokens, saveTokens } from '@/auth/storage';

/**
 * `loading` is a real state, not a detail.
 *
 * Reading SecureStore and verifying the token with the server takes a few
 * hundred milliseconds. Without a distinct loading state the app would default
 * to "logged out", flash the login screen, and then replace it — every single
 * launch, for users who are in fact signed in.
 */
export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

interface AuthContextValue {
  status: AuthStatus;
  user: authApi.User | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<authApi.User | null>(null);

  // A ref, not state, because the API client needs the token *synchronously*
  // while building a request. Reading it from state would hand out whatever
  // value was captured at the last render, which after a refresh is the token we
  // just replaced.
  const tokens = useRef<{ access: string; refresh: string } | null>(null);

  const applySession = useCallback(
    async (result: authApi.AuthResult) => {
      tokens.current = { access: result.access_token, refresh: result.refresh_token };
      await saveTokens({ accessToken: result.access_token, refreshToken: result.refresh_token });
      setUser(result.user);
      setStatus('authenticated');
    },
    [],
  );

  const endSession = useCallback(async () => {
    tokens.current = null;
    await clearTokens();
    setUser(null);
    setStatus('unauthenticated');
  }, []);

  /* ---- wire the API client ------------------------------------------- */

  useEffect(() => {
    configureAuth({
      getAccessToken: () => tokens.current?.access ?? null,

      refreshSession: async () => {
        const refreshToken = tokens.current?.refresh;
        if (!refreshToken) return null;
        try {
          const pair = await authApi.refreshTokens(refreshToken);
          tokens.current = { access: pair.access_token, refresh: pair.refresh_token };
          await saveTokens({
            accessToken: pair.access_token,
            refreshToken: pair.refresh_token,
          });
          return pair.access_token;
        } catch {
          // The refresh token is spent, revoked, or the session was killed by
          // theft detection. Either way there is nothing to recover.
          return null;
        }
      },

      onSessionExpired: () => {
        void endSession();
      },
    });
  }, [endSession]);

  /* ---- restore a session on launch ------------------------------------ */

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const stored = await loadTokens();
      if (!stored) {
        if (!cancelled) setStatus('unauthenticated');
        return;
      }

      tokens.current = { access: stored.accessToken, refresh: stored.refreshToken };

      try {
        // Verify with the server rather than trusting what is on disk. A stored
        // token proves only that we were signed in *once* — it may have expired,
        // been revoked by "sign out everywhere", or belong to a deleted account.
        // This call also transparently refreshes via the client's 401 handling,
        // so a user returning after a week is signed straight back in.
        const me = await authApi.getCurrentUser();
        if (cancelled) return;
        setUser(me);
        setStatus('authenticated');
      } catch {
        if (cancelled) return;
        // Any failure ends the session, including a network error. That is a
        // deliberate simplification: a network failure is not proof the session
        // is invalid, but we cannot confirm it either, and a logged-in shell
        // with no working API is worse than asking for a login.
        //
        // The cost is that opening the app with no signal logs you out. Phase 6
        // handles offline properly, and this is one of the things it should
        // revisit — by then there will be cached data worth staying logged in
        // for.
        await endSession();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [endSession]);

  /* ---- actions --------------------------------------------------------- */

  const signIn = useCallback(
    async (email: string, password: string) => {
      // Errors deliberately propagate to the calling screen, which is what shows
      // the message. Swallowing them here would leave the form with no way to
      // tell the user their password was wrong.
      await applySession(await authApi.login(email.trim(), password));
    },
    [applySession],
  );

  const signUp = useCallback(
    async (email: string, password: string) => {
      await applySession(await authApi.register(email.trim(), password));
    },
    [applySession],
  );

  const signOut = useCallback(async () => {
    const refreshToken = tokens.current?.refresh;
    // Clear locally first, and never let a failed network call block it. If the
    // server is unreachable, the user still expects the app to sign them out —
    // the server-side token simply expires on its own schedule.
    await endSession();
    if (refreshToken) {
      try {
        await authApi.logout(refreshToken);
      } catch {
        // Already signed out locally; nothing useful to report.
      }
    }
  }, [endSession]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, signIn, signUp, signOut }),
    [status, user, signIn, signUp, signOut],
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
