/**
 * Session storage for Supabase, on the device keystore.
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
 * access tokens for that account until it is revoked. Plaintext is not an
 * option, and every Supabase example that reaches for AsyncStorage is making a
 * trade it does not mention.
 *
 * SecureStore uses the iOS Keychain and, on Android, EncryptedSharedPreferences
 * backed by the hardware Keystore. The encryption key lives in hardware the OS
 * controls and the app never sees, so reading the file gets you ciphertext.
 *
 * **The problem this file exists to solve.** Android caps a SecureStore value at
 * roughly 2048 bytes. Our own JWTs were kept deliberately small for that reason.
 * A Supabase session is not ours to keep small: it is one JSON blob holding the
 * access token, the refresh token and the whole user object, and it routinely
 * runs past 2 KB. Handed to SecureStore whole it fails — on Android, on a real
 * device, after login has apparently succeeded.
 *
 * So values are split across numbered keys and rejoined on read. The chunk size
 * is in *characters*, not bytes, and 600 is chosen so that even if every
 * character were a three-byte one the chunk stays under 1800 bytes. Sessions are
 * almost entirely ASCII, so in practice this is far more headroom than needed —
 * which is the right way round for a limit whose failure only shows up on one
 * platform, on a real device, after login has apparently worked.
 *
 * One inherited caveat: Android clears SecureStore on uninstall, iOS keeps the
 * Keychain. A reinstall on iOS can therefore find a stale session, so it is
 * always treated as a *claim* to verify with Supabase, never as proof.
 */

import * as SecureStore from 'expo-secure-store';

/** See the note above on why this is characters and why it is this small. */
const CHUNK_SIZE = 600;

/** How many chunks a key was split into. Absent means nothing is stored. */
const countKey = (key: string) => `${key}.chunks`;
const chunkKey = (key: string, index: number) => `${key}.${index}`;

/**
 * SecureStore is unavailable on web (there is no Keychain in a browser), where
 * the module throws on use. Failing softly keeps the web target usable for
 * development rather than crashing it; the user simply logs in again.
 */
async function available(): Promise<boolean> {
  try {
    return await SecureStore.isAvailableAsync();
  } catch {
    return false;
  }
}

async function clearChunks(key: string, upTo: number): Promise<void> {
  const deletions: Promise<void>[] = [];
  for (let index = 0; index < upTo; index += 1) {
    deletions.push(SecureStore.deleteItemAsync(chunkKey(key, index)));
  }
  await Promise.all(deletions);
}

/**
 * The storage interface supabase-js expects.
 *
 * Shaped to its contract rather than ours: every method resolves rather than
 * throwing, because a storage failure should log the user out, not crash the app
 * on launch.
 */
export const secureSessionStorage = {
  async getItem(key: string): Promise<string | null> {
    if (!(await available())) return null;

    const count = Number(await SecureStore.getItemAsync(countKey(key)));
    if (!Number.isInteger(count) || count <= 0) return null;

    const chunks = await Promise.all(
      Array.from({ length: count }, (_, index) => SecureStore.getItemAsync(chunkKey(key, index))),
    );

    // A missing chunk means a write was interrupted — the app killed mid-save,
    // or storage cleared underneath us. A partial session is worse than none: it
    // would parse as JSON only by luck and otherwise produce a corrupt token.
    // Treat it as absent and make the user sign in again.
    if (chunks.some((chunk) => chunk === null)) return null;

    return chunks.join('');
  },

  async setItem(key: string, value: string): Promise<void> {
    if (!(await available())) return;

    const chunks: string[] = [];
    for (let offset = 0; offset < value.length; offset += CHUNK_SIZE) {
      chunks.push(value.slice(offset, offset + CHUNK_SIZE));
    }

    // Chunks left over from a longer previous session would otherwise sit there
    // forever, and a later shorter write would leave a mixture of the two.
    const previous = Number(await SecureStore.getItemAsync(countKey(key)));
    if (Number.isInteger(previous) && previous > chunks.length) {
      await clearChunks(key, previous);
    }

    await Promise.all(
      chunks.map((chunk, index) => SecureStore.setItemAsync(chunkKey(key, index), chunk)),
    );
    // The count is written *last*. An interrupted save then leaves the old count
    // pointing at chunks that may be half-replaced — which the missing-chunk
    // check above catches — rather than a new count pointing at chunks that were
    // never written.
    await SecureStore.setItemAsync(countKey(key), String(chunks.length));
  },

  async removeItem(key: string): Promise<void> {
    if (!(await available())) return;

    const count = Number(await SecureStore.getItemAsync(countKey(key)));
    if (Number.isInteger(count) && count > 0) {
      await clearChunks(key, count);
    }
    await SecureStore.deleteItemAsync(countKey(key));
  },
};
