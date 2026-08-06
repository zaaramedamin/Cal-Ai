/**
 * Turning an `ApiError` into words a user reads, in their language.
 *
 * This replaces `ApiError.userMessage`, which was English baked into a class
 * that has no access to the dictionary. Every screen called it the same way:
 *
 *     caught instanceof ApiError ? caught.userMessage : 'Could not load X.'
 *
 * — so the fallback was translated and the message that actually appeared most
 * of the time was not. One helper fixes every call site at once.
 *
 * **The server's own `detail` is passed through untranslated, on purpose.** When
 * the backend explains *why* something failed — which nutrient was missing,
 * which cap was hit and for how long — that sentence is more useful than a
 * generic translated one, and it is written in English because the API is. The
 * fix for that is the API returning keys rather than prose, which is a change to
 * the contract and not to this file. Everything the client can answer on its own
 * is translated here.
 */

import { ApiError } from '@/api/client';
import type { Translate } from '@/i18n';
import type { StringKey } from '@/i18n/strings';

/**
 * @param fallback Shown when the failure is not an `ApiError` at all — a bug in
 *   our own code rather than anything the network did. Each screen passes its
 *   own, because "could not load your day" and "could not save that meal" send
 *   the reader to different places.
 */
export function apiErrorMessage(t: Translate, caught: unknown, fallback: StringKey): string {
  if (!(caught instanceof ApiError)) return t(fallback);

  if (caught.isRateLimited && caught.retryAfterSeconds) {
    return t('error.rateLimited', { wait: formatWait(t, caught.retryAfterSeconds) });
  }

  if (caught.detail) return caught.detail;

  switch (caught.kind) {
    case 'timeout':
      return t('error.timeout');
    case 'network':
      return t('error.network');
    case 'parse':
      return t('error.parse');
    default:
      return t('error.server');
  }
}

/** "45 seconds" / "2 minutes", rounded up so the advice is never optimistic. */
function formatWait(t: Translate, seconds: number): string {
  if (seconds < 60) {
    return seconds === 1 ? t('error.waitSecond') : t('error.waitSeconds', { count: seconds });
  }
  const minutes = Math.ceil(seconds / 60);
  return minutes === 1 ? t('error.waitMinute') : t('error.waitMinutes', { count: minutes });
}
