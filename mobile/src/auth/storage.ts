/**
 * Token storage.
 *
 * **Why expo-secure-store and not AsyncStorage.**
 *
 * AsyncStorage writes plaintext. On Android it is an unencrypted file inside the
 * app's sandbox; on iOS it is an unencrypted file in the app container. The
 * sandbox stops *other apps* reading it, and that is all it does — on a rooted
 * or jailbroken device, or in an unencrypted device backup, the contents are
 * readable with no tooling at all.
 *
 * A refresh token is a long-lived credential: anyone holding ours can mint
 * access tokens for that account for thirty days. Plaintext is not an option.
 *
 * SecureStore uses the iOS Keychain and, on Android, EncryptedSharedPreferences
 * backed by the hardware-backed Keystore. The encryption key lives in hardware
 * the OS controls and the app never sees, so reading the file gets you
 * ciphertext.
 *
 * Two constraints this imposes, worth knowing before they bite:
 *
 * 1. Android caps a value at roughly 2048 bytes. That is why the backend's JWT
 *    carries only `sub`, `iat`, `exp` and `type` — piling claims into it would
 *    eventually push past the limit and start failing on real devices.
 * 2. Android clears SecureStore on uninstall; iOS keeps the Keychain. So on iOS
 *    a reinstall can find a stale token. Every entry point treats a stored token
 *    as a *claim* to verify against the server, never as proof of a session.
 */

import * as SecureStore from 'expo-secure-store';

const ACCESS_TOKEN_KEY = 'calai.access_token';
const REFRESH_TOKEN_KEY = 'calai.refresh_token';

export interface StoredTokens {
  accessToken: string;
  refreshToken: string;
}

/**
 * SecureStore is unavailable on web (there is no Keychain in a browser), where
 * the module throws on use. Phase 0's connection check runs on web, so failing
 * softly keeps the web target usable for development rather than crashing it.
 * Nothing sensitive is persisted there — the user simply has to log in again.
 */
const isAvailable = async (): Promise<boolean> => {
  try {
    return await SecureStore.isAvailableAsync();
  } catch {
    return false;
  }
};

export async function saveTokens(tokens: StoredTokens): Promise<void> {
  if (!(await isAvailable())) return;
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, tokens.accessToken),
    SecureStore.setItemAsync(REFRESH_TOKEN_KEY, tokens.refreshToken),
  ]);
}

export async function loadTokens(): Promise<StoredTokens | null> {
  if (!(await isAvailable())) return null;

  const [accessToken, refreshToken] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.getItemAsync(REFRESH_TOKEN_KEY),
  ]);

  // Both or neither. A half-written pair — possible if the app was killed
  // mid-write — is treated as no session at all, because an access token with no
  // refresh token would strand the user with a session that dies in 15 minutes
  // and cannot renew.
  if (!accessToken || !refreshToken) return null;
  return { accessToken, refreshToken };
}

export async function clearTokens(): Promise<void> {
  if (!(await isAvailable())) return;
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}
