/**
 * Turning a Supabase auth failure into something a user can act on.
 *
 * **Why this file exists.** The form used to render `error instanceof ApiError ?
 * error.userMessage : t('common.error')`. Supabase throws `AuthError`, which is
 * not `ApiError`, so *every* failure — wrong password, unconfirmed email, an
 * unconfigured build — collapsed into "Something went wrong". That is useless to
 * the user and actively misleading to whoever debugs it: it hides a missing
 * environment variable behind the same words as a typo'd password.
 *
 * Failures are therefore classified by the code Supabase sends, not by matching
 * on message text, which is localised and rewritten between releases.
 */

import { AuthError } from '@supabase/supabase-js';

import { supabaseConfigured } from '@/auth/supabase';
import type { StringKey } from '@/i18n/strings';

/**
 * The translation key describing what actually went wrong.
 *
 * Falls back to the generic message only for failures with no recognised code,
 * which is now the rare case rather than the only one.
 */
export function authErrorKey(error: unknown): StringKey {
  // Checked first: with no URL or key every call fails as a network error, and
  // "check your connection" would send the user to their wifi settings over a
  // missing build variable.
  if (!supabaseConfigured) return 'auth.errNotConfigured';

  if (error instanceof AuthError) {
    switch (error.code) {
      case 'invalid_credentials':
      case 'invalid_grant':
        return 'auth.errInvalidCredentials';
      case 'email_not_confirmed':
        return 'auth.errEmailNotConfirmed';
      case 'user_already_exists':
      case 'email_exists':
        return 'auth.errUserExists';
      case 'weak_password':
        return 'auth.errWeakPassword';
      // Project misconfiguration rather than anything the user did. Named
      // explicitly because the generic message sent us hunting through env
      // vars and bundler caches for a setting that was two clicks away.
      case 'email_provider_disabled':
        return 'auth.errProviderDisabled';
      case 'signup_disabled':
        return 'auth.errSignupDisabled';
      case 'over_request_rate_limit':
      case 'over_email_send_rate_limit':
        return 'auth.errRateLimited';
      default:
        break;
    }

    // Retryable fetch failures carry no code, and a status of 0 or none means
    // the request never reached Supabase at all.
    if (error.status === undefined || error.status === 0) return 'auth.errNetwork';
    if (error.status === 429) return 'auth.errRateLimited';
  }

  // A bare TypeError from fetch is what React Native raises when the host is
  // unreachable — a phone off wifi, or a URL that does not resolve.
  if (error instanceof TypeError) return 'auth.errNetwork';

  return 'auth.somethingWrong';
}
